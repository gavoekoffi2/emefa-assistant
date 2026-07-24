"""Himalaya CLI adapter for the temporary EMEFA email account."""

from __future__ import annotations

import json
import re
import shlex
import smtplib
import ssl
import subprocess
import tomllib
from collections.abc import Mapping
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from typing import Any

_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


class EmailProviderError(RuntimeError):
    pass


class HimalayaEmailProvider:
    def __init__(
        self,
        account: str,
        binary: str = "himalaya",
        config: Path | None = None,
        timeout: float = 30.0,
        sender: str | None = None,
    ):
        self.account = account
        self.binary = binary
        self.config = config
        self.timeout = timeout
        self.sender = sender or self._sender_from_config()
        self.smtp = self._smtp_from_config()

    def _sender_from_config(self) -> str | None:
        fallback = self.account if _EMAIL.fullmatch(self.account) else None
        if self.config is None:
            return fallback
        try:
            data = tomllib.loads(self.config.read_text(encoding="utf-8"))
            sender = str(data["accounts"][self.account]["email"]).strip()
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            return fallback
        return sender if _EMAIL.fullmatch(sender) else fallback

    def _smtp_from_config(self) -> Mapping[str, Any] | None:
        if self.config is None:
            return None
        try:
            data = tomllib.loads(self.config.read_text(encoding="utf-8"))
            backend = data["accounts"][self.account]["message"]["send"]["backend"]
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            return None
        return backend if isinstance(backend, Mapping) and backend.get("type") == "smtp" else None

    def _smtp_password(self) -> str:
        if self.smtp is None:
            raise EmailProviderError("email_smtp_not_configured")
        auth = self.smtp.get("auth")
        command = auth.get("cmd") if isinstance(auth, Mapping) else None
        if not isinstance(command, str) or not command.strip():
            raise EmailProviderError("email_smtp_auth_not_configured")
        try:
            completed = subprocess.run(
                shlex.split(command), capture_output=True, text=True,
                timeout=self.timeout, check=False,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise EmailProviderError("email_smtp_auth_unavailable") from exc
        password = completed.stdout.strip()
        if completed.returncode != 0 or not password:
            raise EmailProviderError("email_smtp_auth_unavailable")
        return password

    def _send_smtp(self, message: EmailMessage) -> None:
        if self.smtp is None or self.sender is None:
            raise EmailProviderError("email_smtp_not_configured")
        host = str(self.smtp.get("host", "")).strip()
        port = int(self.smtp.get("port", 0))
        encryption = self.smtp.get("encryption")
        encryption_type = (
            str(encryption.get("type", "")).strip()
            if isinstance(encryption, Mapping) else ""
        )
        if not host or not 1 <= port <= 65535:
            raise EmailProviderError("email_smtp_not_configured")
        password = self._smtp_password()
        context = ssl.create_default_context()
        try:
            if encryption_type == "tls":
                with smtplib.SMTP_SSL(host, port, timeout=self.timeout, context=context) as server:
                    server.login(self.sender, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=self.timeout) as server:
                    server.ehlo()
                    if encryption_type in {"start-tls", "starttls"}:
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(self.sender, password)
                    server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailProviderError("email_operation_failed") from exc

    def _run(self, args: list[str]) -> Any:
        command = [self.binary]
        if self.config is not None:
            command += ["-c", str(self.config)]
        command += ["-o", "json", *args]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EmailProviderError("email_provider_unavailable") from exc
        if completed.returncode != 0:
            raise EmailProviderError("email_operation_failed")
        if len(completed.stdout) > 2_000_000:
            raise EmailProviderError("email_response_too_large")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise EmailProviderError("email_invalid_response") from exc

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 20))
        args = ["envelope", "list", "-a", self.account, "--page", "1", "--page-size", str(safe_limit)]
        query = query.strip()[:300]
        if query:
            args.extend(["subject", query, "or", "body", query])
        data = self._run(args)
        if not isinstance(data, list):
            raise EmailProviderError("email_invalid_response")
        messages = []
        for item in data[:safe_limit]:
            if not isinstance(item, Mapping):
                continue
            sender = item.get("from")
            if isinstance(sender, Mapping):
                sender = sender.get("addr") or sender.get("name") or ""
            messages.append({
                "id": str(item.get("id", "")),
                "from": str(sender or ""),
                "subject": str(item.get("subject", ""))[:500],
                "date": str(item.get("date", "")),
                "flags": list(item.get("flags", [])) if isinstance(item.get("flags"), list) else [],
            })
        return messages

    def read(self, message_id: str) -> dict[str, Any]:
        message_id = str(message_id).strip()
        if not message_id.isdigit():
            raise ValueError("invalid_message_id")
        content = self._run(["message", "read", message_id, "-a", self.account, "--preview"])
        if not isinstance(content, str):
            raise EmailProviderError("email_invalid_response")
        return {"id": message_id, "content": content[:100_000]}

    def _email_message(
        self, to: str, subject: str, body: str, *, require_sender: bool = False
    ) -> EmailMessage:
        to = to.strip()
        subject = subject.strip()
        if not _EMAIL.fullmatch(to):
            raise ValueError("invalid_recipient")
        if not subject or len(subject) > 500 or "\n" in subject or "\r" in subject:
            raise ValueError("invalid_subject")
        if not body.strip() or len(body) > 50_000:
            raise ValueError("invalid_body")
        message = EmailMessage(policy=SMTP)
        if self.sender:
            message["From"] = self.sender
        elif require_sender:
            raise EmailProviderError("email_sender_not_configured")
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _message(self, to: str, subject: str, body: str, *, require_sender: bool = False) -> str:
        return self._email_message(
            to, subject, body, require_sender=require_sender
        ).as_string()

    def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        self._run(["message", "save", "-a", self.account, "-f", "[Gmail]/Drafts", self._message(to, subject, body)])
        return {"status": "draft_created", "to": to, "subject": subject}

    def send(self, to: str, subject: str, body: str) -> dict[str, Any]:
        message = self._email_message(to, subject, body, require_sender=True)
        if self.smtp is not None:
            self._send_smtp(message)
        else:
            self._run(["message", "send", "-a", self.account, message.as_string()])
        return {"status": "sent", "to": to, "subject": subject}
