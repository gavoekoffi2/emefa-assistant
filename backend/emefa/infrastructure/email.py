"""Provider-neutral e-mail over SMTP (send) and IMAP (search/read/draft).

Standard protocols keep EMEFA free of vendor lock-in: the same adapters
work with Gmail (app password), Outlook, or any hosting provider.
Credentials come from server-side settings only and never reach the
model or the browser.
"""

from __future__ import annotations

import asyncio
import imaplib
import smtplib
import ssl
import time
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage
from typing import Any


@dataclass(slots=True)
class SmtpEmailSender:
    host: str
    port: int
    sender: str
    username: str | None = None
    password: str | None = None
    starttls: bool = True
    timeout: float = 20.0

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender)

    async def send(self, to: str, subject: str, body: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._send_sync, to, subject, body)

    def _send_sync(self, to: str, subject: str, body: str) -> dict[str, Any]:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as client:
            if self.starttls:
                client.starttls(context=ssl.create_default_context())
            if self.username and self.password:
                client.login(self.username, self.password)
            refused = client.send_message(message)
        # smtplib returns a dict of refused recipients; empty means accepted.
        return {"accepted": not refused, "refused_recipients": sorted(refused)}


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _text_body(message, limit: int = 4_000) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:limit]
        return "(aucun corps texte lisible)"
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")[:limit]


_DRAFT_MAILBOXES = ("[Gmail]/Drafts", "Drafts", "INBOX.Drafts", "Brouillons")


@dataclass(slots=True)
class ImapEmailClient:
    host: str
    port: int = 993
    username: str | None = None
    password: str | None = None
    timeout: float = 20.0

    @property
    def configured(self) -> bool:
        return bool(self.host and self.username and self.password)

    async def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def read(self, uid: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._read_sync, uid)

    async def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._create_draft_sync, to, subject, body)

    def _connect(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout)
        client.login(self.username or "", self.password or "")
        return client

    @staticmethod
    def _sanitize_query(query: str) -> str:
        # Strip quotes and any control characters (CR/LF included) so a
        # model- or user-supplied query cannot inject IMAP protocol commands.
        neutralised = "".join(ch if ch >= " " and ch != '"' else " " for ch in query)
        return " ".join(neutralised.split())[:200]

    def _search_sync(self, query: str, limit: int) -> list[dict[str, Any]]:
        client = self._connect()
        try:
            client.select("INBOX", readonly=True)
            cleaned = self._sanitize_query(query)
            if cleaned:
                _, data = client.uid("search", None, "TEXT", f'"{cleaned}"')
            else:
                _, data = client.uid("search", None, "ALL")
            uids = (data[0] or b"").split()[-limit:]
            results = []
            for uid in reversed(uids):
                _, fetched = client.uid(
                    "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
                )
                raw = next(
                    (part[1] for part in fetched if isinstance(part, tuple)), b""
                )
                headers = message_from_bytes(raw)
                results.append(
                    {
                        "uid": uid.decode(),
                        "from": _decode(headers.get("From")),
                        "subject": _decode(headers.get("Subject")),
                        "date": _decode(headers.get("Date")),
                    }
                )
            return results
        finally:
            client.logout()

    def _read_sync(self, uid: str) -> dict[str, Any] | None:
        client = self._connect()
        try:
            client.select("INBOX", readonly=True)
            _, fetched = client.uid("fetch", uid.encode(), "(BODY.PEEK[])")
            raw = next((part[1] for part in fetched if isinstance(part, tuple)), None)
            if not raw:
                return None
            message = message_from_bytes(raw)
            return {
                "uid": uid,
                "from": _decode(message.get("From")),
                "to": _decode(message.get("To")),
                "subject": _decode(message.get("Subject")),
                "date": _decode(message.get("Date")),
                "body": _text_body(message),
            }
        finally:
            client.logout()

    def _create_draft_sync(self, to: str, subject: str, body: str) -> dict[str, Any]:
        message = EmailMessage()
        message["From"] = self.username or ""
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        client = self._connect()
        try:
            for mailbox in _DRAFT_MAILBOXES:
                status, _ = client.append(
                    mailbox,
                    r"(\Draft)",
                    imaplib.Time2Internaldate(time.time()),
                    message.as_bytes(),
                )
                if status == "OK":
                    return {"draft_saved": True, "mailbox": mailbox}
            return {"draft_saved": False, "error": "no_drafts_mailbox"}
        finally:
            client.logout()
