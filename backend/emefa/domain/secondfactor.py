"""WebAuthn second factor — face unlock that actually holds (ADR-005).

The important thing about this module is what it does *not* contain: no face
image, no embedding, no template, no comparison. The biometric never leaves
the user's device. What is stored here is a public key, and what is verified
is a signature over a challenge this server issued.

That is the whole reason this design was chosen over an in-browser face
embedding. An embedding computed by JavaScript on a device the attacker
controls is not a second factor — anyone who can open a console can post a
stored vector and never show a face. Here the private key lives in the
device's secure enclave and is released only after the OS has verified the
user with hardware the page cannot influence.

Three server-side invariants, each of which is a real attack if dropped:

* **Challenges are single-use.** Consumed on verification, so a captured
  assertion cannot be replayed.
* **The signature counter never goes backwards.** A regression is the standard
  signal of a cloned authenticator.
* **The credential's account binding is read from our own storage**, never
  from what the client claimed.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from emefa.domain import storage
from emefa.domain.scope import Scope

#: How long an issued challenge stays usable. Long enough to look at a camera,
#: short enough that a captured one is worthless.
CHALLENGE_TTL_SECONDS = 180

#: How long a step-up counts for. Short: the point of the factor is to protect
#: a consequential action, and a step-up from this morning does not.
STEP_UP_TTL_SECONDS = 900

REGISTRATION = "registration"
AUTHENTICATION = "authentication"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).isoformat(timespec="seconds")


class SecondFactorError(Exception):
    """Verification failed. Deliberately carries no detail for the client: the
    difference between "unknown credential" and "bad signature" is useful to an
    attacker and to nobody else."""


@dataclass(frozen=True, slots=True)
class Credential:
    credential_id: str
    account_id: str
    public_key: str
    label: str
    sign_count: int
    created_at: str
    last_used_at: str | None

    def summary(self) -> dict[str, object]:
        return {
            "credential_id": self.credential_id,
            "label": self.label,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }


class SecondFactorRepository:
    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        self.database_path = database_path
        self.scope = scope
        storage.run_migrations(database_path)

    def for_scope(self, scope: Scope) -> "SecondFactorRepository":
        return SecondFactorRepository(self.database_path, scope)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    # ── challenges ────────────────────────────────────────────────────────

    def issue_challenge(self, purpose: str, account_id: str | None = None) -> str:
        """A fresh, server-generated challenge. The client never chooses it —
        a client-chosen challenge is a signature the attacker can pre-compute."""
        challenge = secrets.token_urlsafe(32)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO webauthn_challenges (challenge, account_id, purpose, created_at) "
                "VALUES (?, ?, ?, ?)",
                (challenge, account_id, purpose, _stamp()),
            )
        return challenge

    def consume_challenge(self, challenge: str, purpose: str) -> str | None:
        """Spend a challenge. Returns the account it was issued for.

        Deleting before checking the age is deliberate: a stale challenge must
        not be retryable, and neither must a valid one.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT account_id, purpose, created_at FROM webauthn_challenges "
                "WHERE challenge = ?",
                (challenge,),
            ).fetchone()
            connection.execute(
                "DELETE FROM webauthn_challenges WHERE challenge = ?", (challenge,)
            )
            # Opportunistic sweep, so abandoned challenges do not accumulate.
            connection.execute(
                "DELETE FROM webauthn_challenges WHERE created_at < ?",
                (_stamp(_now() - timedelta(seconds=CHALLENGE_TTL_SECONDS * 4)),),
            )
        if row is None or row["purpose"] != purpose:
            raise SecondFactorError("challenge")
        try:
            issued = datetime.fromisoformat(row["created_at"])
        except ValueError as error:
            raise SecondFactorError("challenge") from error
        if _now() - issued > timedelta(seconds=CHALLENGE_TTL_SECONDS):
            raise SecondFactorError("challenge")
        return row["account_id"]

    # ── credentials ───────────────────────────────────────────────────────

    def register(
        self,
        credential_id: str,
        account_id: str,
        public_key: str,
        label: str = "",
        sign_count: int = 0,
    ) -> Credential:
        if self.scope is not None and account_id != self.scope.user_id:
            raise SecondFactorError("account")
        with self._connect() as connection:
            tenant_id = self.scope.tenant_id if self.scope is not None else None
            if tenant_id is None:
                owner = connection.execute(
                    "SELECT tenant_id FROM users WHERE user_id = ?", (account_id,)
                ).fetchone()
                tenant_id = owner["tenant_id"] if owner is not None else "default"
            connection.execute(
                "INSERT OR REPLACE INTO webauthn_credentials "
                "(credential_id, tenant_id, account_id, public_key, label, sign_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    credential_id,
                    tenant_id,
                    account_id,
                    public_key,
                    " ".join(label.split()).strip()[:80] or "Cet appareil",
                    max(0, int(sign_count)),
                    _stamp(),
                ),
            )
        found = self.get(credential_id)
        assert found is not None
        return found

    def get(self, credential_id: str) -> Credential | None:
        clause = "WHERE credential_id = ?"
        parameters: tuple[object, ...] = (credential_id,)
        if self.scope is not None:
            clause += " AND tenant_id = ? AND account_id = ?"
            parameters += (self.scope.tenant_id, self.scope.user_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT credential_id, account_id, public_key, label, sign_count, "
                f"created_at, last_used_at FROM webauthn_credentials {clause}",
                parameters,
            ).fetchone()
        return _from_row(row) if row is not None else None

    def for_account(self, account_id: str) -> list[Credential]:
        if self.scope is not None and account_id != self.scope.user_id:
            return []
        clause = "WHERE account_id = ?"
        parameters: tuple[object, ...] = (account_id,)
        if self.scope is not None:
            clause += " AND tenant_id = ?"
            parameters += (self.scope.tenant_id,)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT credential_id, account_id, public_key, label, sign_count, "
                "created_at, last_used_at FROM webauthn_credentials "
                f"{clause} ORDER BY created_at",
                parameters,
            ).fetchall()
        return [_from_row(row) for row in rows]

    def enrolled(self, account_id: str) -> bool:
        return bool(self.for_account(account_id))

    def revoke(self, credential_id: str, account_id: str) -> bool:
        """Remove a credential. Scoped to the account, so a credential id from
        elsewhere cannot delete someone else's factor."""
        if self.scope is not None and account_id != self.scope.user_id:
            return False
        clause = "credential_id = ? AND account_id = ?"
        parameters: tuple[object, ...] = (credential_id, account_id)
        if self.scope is not None:
            clause += " AND tenant_id = ?"
            parameters += (self.scope.tenant_id,)
        with self._connect() as connection:
            deleted = connection.execute(
                f"DELETE FROM webauthn_credentials WHERE {clause}", parameters
            ).rowcount
        return bool(deleted)

    def record_use(self, credential_id: str, sign_count: int) -> None:
        """Advance the counter after a successful assertion.

        Callers must have already refused a regression; this only moves it
        forward, so a lower value can never be written by a later success.
        """
        clause = "credential_id = ?"
        parameters: tuple[object, ...] = (max(0, int(sign_count)), _stamp(), credential_id)
        if self.scope is not None:
            clause += " AND tenant_id = ? AND account_id = ?"
            parameters += (self.scope.tenant_id, self.scope.user_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE webauthn_credentials SET sign_count = MAX(sign_count, ?), "
                f"last_used_at = ? WHERE {clause}", parameters
            )

    def check_counter(self, credential: Credential, new_count: int) -> None:
        """A counter that goes backwards means two authenticators are claiming
        to be the same credential — the standard clone signal.

        Authenticators that report zero are exempt: many platform
        authenticators do not implement a counter at all, and treating that as
        a clone would lock out every Apple device.
        """
        if new_count == 0 and credential.sign_count == 0:
            return
        if new_count <= credential.sign_count and credential.sign_count > 0:
            raise SecondFactorError("counter")

    # ── step-up state ─────────────────────────────────────────────────────

    def mark_verified(self, device_id: str) -> None:
        clause = "device_id = ?"
        parameters: tuple[object, ...] = (_stamp(), device_id)
        if self.scope is not None:
            clause += " AND user_id = ?"
            parameters += (self.scope.user_id,)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE devices SET second_factor_at = ? WHERE {clause}", parameters
            )

    def verified_recently(self, device_id: str) -> bool:
        clause = "WHERE device_id = ?"
        parameters: tuple[object, ...] = (device_id,)
        if self.scope is not None:
            clause += " AND user_id = ?"
            parameters += (self.scope.user_id,)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT second_factor_at FROM devices {clause}", parameters
            ).fetchone()
        if row is None or not row["second_factor_at"]:
            return False
        try:
            moment = datetime.fromisoformat(row["second_factor_at"])
        except ValueError:
            return False
        return _now() - moment <= timedelta(seconds=STEP_UP_TTL_SECONDS)

    def clear_verification(self, device_id: str) -> None:
        clause = "device_id = ?"
        parameters: tuple[object, ...] = (device_id,)
        if self.scope is not None:
            clause += " AND user_id = ?"
            parameters += (self.scope.user_id,)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE devices SET second_factor_at = NULL WHERE {clause}", parameters
            )


def _from_row(row: sqlite3.Row) -> Credential:
    return Credential(
        credential_id=row["credential_id"],
        account_id=row["account_id"],
        public_key=row["public_key"],
        label=row["label"],
        sign_count=int(row["sign_count"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )
