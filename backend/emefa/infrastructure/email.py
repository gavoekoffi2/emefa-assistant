"""Himalaya CLI adapter for the temporary EMEFA email account."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


class EmailProviderError(RuntimeError):
    pass


class HimalayaEmailProvider:
    def __init__(self, account: str, binary: str = "himalaya", config: Path | None = None, timeout: float = 30.0):
        self.account = account
        self.binary = binary
        self.config = config
        self.timeout = timeout

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

    @staticmethod
    def _template(to: str, subject: str, body: str) -> str:
        to = to.strip()
        subject = subject.strip()
        if not _EMAIL.fullmatch(to):
            raise ValueError("invalid_recipient")
        if not subject or len(subject) > 500 or "\n" in subject or "\r" in subject:
            raise ValueError("invalid_subject")
        if not body.strip() or len(body) > 50_000:
            raise ValueError("invalid_body")
        return f"To: {to}\nSubject: {subject}\n\n{body}"

    def create_draft(self, to: str, subject: str, body: str) -> dict[str, Any]:
        self._run(["template", "save", "-a", self.account, "-f", "[Gmail]/Drafts", self._template(to, subject, body)])
        return {"status": "draft_created", "to": to, "subject": subject}

    def send(self, to: str, subject: str, body: str) -> dict[str, Any]:
        self._run(["template", "send", "-a", self.account, self._template(to, subject, body)])
        return {"status": "sent", "to": to, "subject": subject}
