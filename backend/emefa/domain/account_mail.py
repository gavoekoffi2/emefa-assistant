"""Delivery of the links that prove someone owns an address.

Verification, password-reset and invitation tokens are useless unless they
reach a mailbox, and dangerous if they reach anything else. This module is the
only place that turns a token into a message, so there is one thing to review.

Two deliberate rules:

* a token is **never** returned in an HTTP response. Doing so would make
  "verified email" mean nothing, because whoever called the endpoint would
  already hold the proof;
* when no email provider is configured the link is written to the server log
  instead, at WARNING, clearly marked. An operator bootstrapping the first
  account can read it out of the container logs; a passing HTTP client cannot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

from emefa.domain.email import EmailProvider

logger = logging.getLogger("emefa.accounts.mail")


@dataclass(frozen=True, slots=True)
class Delivery:
    """What happened to a link, so the API can answer honestly."""

    channel: str  # "email" | "server_log"
    delivered: bool


class AccountMailer:
    def __init__(
        self,
        base_url: str,
        provider: EmailProvider | None = None,
        sender_name: str = "EMEFA",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.sender_name = sender_name

    def _link(self, path: str, token: str) -> str:
        return f"{self.base_url}{path}?token={quote(token)}"

    def _send(self, to: str, subject: str, body: str, kind: str) -> Delivery:
        if self.provider is None:
            # Marked, single-line, and never at INFO: this is an operator
            # bootstrap path, not something to leave on in production.
            logger.warning(
                "account link not emailed — no provider configured",
                extra={"kind": kind, "recipient": to, "body": body},
            )
            return Delivery(channel="server_log", delivered=False)
        try:
            self.provider.send(to=to, subject=subject, body=body)
        except Exception:  # noqa: BLE001 - delivery must not break signup
            logger.exception("account link delivery failed", extra={"kind": kind})
            return Delivery(channel="email", delivered=False)
        return Delivery(channel="email", delivered=True)

    def send_verification(self, *, to: str, display_name: str, token: str) -> Delivery:
        link = self._link("/verifier-email", token)
        body = (
            f"Bonjour {display_name},\n\n"
            f"Confirmez votre adresse pour activer votre espace {self.sender_name} :\n"
            f"{link}\n\n"
            "Ce lien est valable trois jours. Si vous n'êtes pas à l'origine de cette "
            "demande, ignorez ce message.\n"
        )
        return self._send(to, f"Confirmez votre adresse {self.sender_name}", body, "verification")

    def send_password_reset(self, *, to: str, display_name: str, token: str) -> Delivery:
        link = self._link("/nouveau-mot-de-passe", token)
        body = (
            f"Bonjour {display_name},\n\n"
            "Vous avez demandé à réinitialiser votre mot de passe :\n"
            f"{link}\n\n"
            "Ce lien est valable deux heures et ne fonctionne qu'une fois. "
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
            "votre mot de passe actuel reste valable.\n"
        )
        return self._send(to, f"Réinitialiser votre mot de passe {self.sender_name}", body, "reset")

    def send_invitation(
        self, *, to: str, company_name: str, inviter_name: str, role_label: str, token: str
    ) -> Delivery:
        link = self._link("/rejoindre", token)
        body = (
            f"Bonjour,\n\n"
            f"{inviter_name} vous invite à rejoindre {company_name} sur "
            f"{self.sender_name} en tant que {role_label.lower()} :\n"
            f"{link}\n\n"
            "Ce lien est valable quatorze jours.\n"
        )
        return self._send(to, f"Rejoindre {company_name} sur {self.sender_name}", body, "invitation")
