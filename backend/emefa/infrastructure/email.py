"""Provider-neutral outbound e-mail over SMTP.

SMTP keeps EMEFA free of vendor lock-in: the same adapter works with
Gmail (app password), Outlook, or any hosting provider. Credentials come
from server-side settings only and never reach the model or the browser.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
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
