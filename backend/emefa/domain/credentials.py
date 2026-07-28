"""Per-tenant connected accounts, encrypted at rest.

    Tenant A · Jean  · jean@gmail.com  · encrypted token
    Tenant B · Amina · amina@gmail.com · encrypted token

Two mechanisms keep those rows apart, and the second is the one that matters:

1. **Scoped queries.** Every read and write takes an :class:`AccountScope` and
   puts ``tenant_id`` and ``user_id`` in the ``WHERE`` clause. There is no
   method that can return a credential without a scope — isolation cannot be
   forgotten at a call site (CLAUDE.md §31).

2. **Scope-bound ciphertext.** The tenant, user and provider are used as the
   AEAD *associated data*, so a ciphertext lifted out of Amina's row and
   written into Jean's row **fails to decrypt**. A SQL mistake, a bad restore
   or a tampered database therefore cannot become a silent cross-tenant read;
   it becomes a loud error.

The vault **fails closed**: with no encryption key configured it refuses to
store a secret rather than falling back to plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.observability import audit

#: Providers a connected account may belong to.
PROVIDERS = ("gmail", "google_calendar", "microsoft_mail", "imap_smtp")
ACCOUNT_STATUSES = ("active", "revoked", "expired")

_KEY_VERSION = 1
_NONCE_BYTES = 12

_COLUMNS = (
    "account_id, tenant_id, user_id, provider, account_label, scopes, status, "
    "expires_at, last_used_at, key_version, created_at, updated_at"
)


class CredentialError(RuntimeError):
    """The vault cannot serve this request safely."""


class VaultNotConfiguredError(CredentialError):
    """No encryption key — refuse rather than store a secret in clear."""


class CredentialDecryptionError(CredentialError):
    """The stored secret does not belong to the scope that asked for it."""


@dataclass(frozen=True, slots=True)
class AccountScope:
    """Who is asking. Every vault operation requires one."""

    tenant_id: str
    user_id: str

    def associated_data(self, provider: str) -> bytes:
        """Binds ciphertext to its owner; changing any part breaks decryption."""
        return f"{self.tenant_id}|{self.user_id}|{provider}".encode("utf-8")


@dataclass(frozen=True, slots=True)
class ConnectedAccount:
    """A connected account as it may be *shown*. Never carries the secret."""

    account_id: str
    tenant_id: str
    user_id: str
    provider: str
    account_label: str
    scopes: str
    status: str
    expires_at: str | None
    last_used_at: str | None
    key_version: int
    created_at: str
    updated_at: str

    def is_usable(self, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        if not self.expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry > (now or datetime.now(timezone.utc))


def derive_key(secret: str) -> bytes:
    """Accept a base64 32-byte key, or stretch any passphrase to one.

    Stretching keeps a short operator-chosen value usable without ever letting
    a non-32-byte key reach the cipher.
    """
    raw = (secret or "").strip()
    if not raw:
        raise VaultNotConfiguredError("no_encryption_key")
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(decoded) == 32:
            return decoded
    except (ValueError, TypeError):
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


class CredentialVault:
    """Stores and serves connected-account secrets, scoped and encrypted."""

    def __init__(self, database_path: Path, encryption_key: str | None) -> None:
        self.database_path = Path(database_path)
        storage.run_migrations(self.database_path)
        self._key = derive_key(encryption_key) if encryption_key else None

    @property
    def configured(self) -> bool:
        return self._key is not None

    # -- encryption -------------------------------------------------------

    def _cipher(self) -> Any:
        if self._key is None:
            raise VaultNotConfiguredError("no_encryption_key")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(self._key)

    def _encrypt(self, secret: str, scope: AccountScope, provider: str) -> tuple[str, str]:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._cipher().encrypt(
            nonce, secret.encode("utf-8"), scope.associated_data(provider)
        )
        return (
            base64.b64encode(ciphertext).decode("ascii"),
            base64.b64encode(nonce).decode("ascii"),
        )

    def _decrypt(
        self, ciphertext: str, nonce: str, scope: AccountScope, provider: str
    ) -> str:
        try:
            plaintext = self._cipher().decrypt(
                base64.b64decode(nonce),
                base64.b64decode(ciphertext),
                scope.associated_data(provider),
            )
        except VaultNotConfiguredError:
            raise
        except Exception as error:
            # Wrong key, wrong tenant, wrong user, wrong provider or tampering
            # all land here — and all of them must be refusals, not guesses.
            raise CredentialDecryptionError("credential_unreadable") from error
        return plaintext.decode("utf-8")

    # -- writes -----------------------------------------------------------

    def connect(
        self,
        scope: AccountScope,
        provider: str,
        account_label: str,
        secret: str,
        scopes: str = "",
        expires_at: str | None = None,
    ) -> ConnectedAccount:
        """Store (or replace) the credential for one provider and one user."""
        if provider not in PROVIDERS:
            raise CredentialError("unknown_provider")
        if not str(secret).strip():
            raise CredentialError("empty_secret")
        if self._key is None:
            # Fail closed: never downgrade to plaintext because a key is absent.
            raise VaultNotConfiguredError("no_encryption_key")

        label = str(account_label).strip()[:200]
        ciphertext, nonce = self._encrypt(str(secret), scope, provider)
        existing = self.describe(scope, provider)
        account_id = existing.account_id if existing else uuid.uuid4().hex
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO connected_accounts (account_id, tenant_id, user_id, provider, "
                "account_label, secret_ciphertext, secret_nonce, key_version, scopes, "
                "status, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?) "
                "ON CONFLICT(tenant_id, user_id, provider) DO UPDATE SET "
                "account_label = excluded.account_label, "
                "secret_ciphertext = excluded.secret_ciphertext, "
                "secret_nonce = excluded.secret_nonce, "
                "key_version = excluded.key_version, scopes = excluded.scopes, "
                "status = 'active', expires_at = excluded.expires_at, "
                "updated_at = CURRENT_TIMESTAMP",
                (
                    account_id, scope.tenant_id, scope.user_id, provider, label,
                    ciphertext, nonce, _KEY_VERSION, str(scopes)[:500], expires_at,
                ),
            )
        # The label is an identifier, not a secret; the token never reaches a log.
        audit(
            "account_connected",
            tenant_id=scope.tenant_id, user_id=scope.user_id,
            provider=provider, account_label=label,
        )
        found = self.describe(scope, provider)
        assert found is not None
        return found

    def revoke(self, scope: AccountScope, provider: str) -> bool:
        """Revoke access and destroy the stored secret."""
        with storage.connect(self.database_path) as connection:
            changed = connection.execute(
                "UPDATE connected_accounts SET status = 'revoked', "
                "secret_ciphertext = '', secret_nonce = '', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE tenant_id = ? AND user_id = ? AND provider = ?",
                (scope.tenant_id, scope.user_id, provider),
            ).rowcount
        if changed:
            audit(
                "account_revoked",
                tenant_id=scope.tenant_id, user_id=scope.user_id, provider=provider,
            )
        return bool(changed)

    def touch(self, scope: AccountScope, provider: str) -> None:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE connected_accounts SET last_used_at = CURRENT_TIMESTAMP "
                "WHERE tenant_id = ? AND user_id = ? AND provider = ?",
                (scope.tenant_id, scope.user_id, provider),
            )

    # -- reads ------------------------------------------------------------

    def describe(self, scope: AccountScope, provider: str) -> ConnectedAccount | None:
        """Metadata only — safe to return to an interface."""
        row = self._one(
            f"SELECT {_COLUMNS} FROM connected_accounts "
            "WHERE tenant_id = ? AND user_id = ? AND provider = ?",
            (scope.tenant_id, scope.user_id, provider),
        )
        return ConnectedAccount(**row) if row else None

    def list(self, scope: AccountScope) -> list[ConnectedAccount]:
        rows = self._all(
            f"SELECT {_COLUMNS} FROM connected_accounts "
            "WHERE tenant_id = ? AND user_id = ? ORDER BY provider",
            (scope.tenant_id, scope.user_id),
        )
        return [ConnectedAccount(**row) for row in rows]

    def secret(self, scope: AccountScope, provider: str) -> str | None:
        """The decrypted secret, for the owner only.

        Returns ``None`` when there is nothing usable to return. Raises when a
        row exists but cannot be decrypted under this scope — that is a
        security event, not an absence.
        """
        row = self._one(
            "SELECT secret_ciphertext, secret_nonce, status, expires_at "
            "FROM connected_accounts WHERE tenant_id = ? AND user_id = ? AND provider = ?",
            (scope.tenant_id, scope.user_id, provider),
        )
        if row is None or not row["secret_ciphertext"]:
            return None
        account = self.describe(scope, provider)
        if account is None or not account.is_usable():
            return None
        return self._decrypt(row["secret_ciphertext"], row["secret_nonce"], scope, provider)

    # -- SQL --------------------------------------------------------------

    def _one(self, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None

    def _all(self, sql: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]
