"""Device identity and token persistence."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from emefa.domain import storage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from emefa.domain.credentials import AccountScope

#: A device is always read together with the tenant that owns it, so no caller
#: can end up holding a device without knowing whose data it may touch.
_DEVICE_COLUMNS = "d.device_id, d.name, d.token_hash, d.user_id, u.tenant_id"
_DEVICE_SOURCE = " FROM devices d LEFT JOIN users u ON u.user_id = d.user_id"


@dataclass(frozen=True, slots=True)
class Device:
    device_id: str
    name: str
    token_hash: str
    #: Owner of this device. Every scoped resource — connected accounts above
    #: all — is resolved from here, never from anything a client can send.
    user_id: str = storage.DEFAULT_USER_ID
    tenant_id: str = storage.DEFAULT_TENANT_ID

    def scope(self) -> "AccountScope":
        from emefa.domain.credentials import AccountScope

        return AccountScope(tenant_id=self.tenant_id, user_id=self.user_id)


class DeviceRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    def schema_version(self) -> int:
        return storage.schema_version(self.database_path)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def count(self, user_id: str | None = None) -> int:
        """Devices overall, or the ones belonging to one account.

        The instance-wide count bounds the single-tenant deployment; the
        per-account count is what a SaaS sign-in checks, so one company
        filling its seats cannot lock another company out.
        """
        with self._connect() as connection:
            if user_id is None:
                row = connection.execute("SELECT COUNT(*) FROM devices").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM devices WHERE user_id = ?", (user_id,)
                ).fetchone()
        return int(row[0]) if row is not None else 0

    def enroll(self, name: str, user_id: str = storage.DEFAULT_USER_ID) -> tuple[Device, str]:
        """Attach a browser to an account and hand back its bearer token.

        The owner is passed in by the caller that just authenticated it — the
        device row is the only place the request path reads a tenant from, so
        it must never be set from anything a client sent.
        """
        token = secrets.token_urlsafe(32)
        device = Device(
            device_id=str(uuid.uuid4()),
            name=name,
            token_hash=self._hash_token(token),
            user_id=user_id,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO devices (device_id, name, token_hash, user_id) "
                "VALUES (?, ?, ?, ?)",
                (device.device_id, device.name, device.token_hash, device.user_id),
            )
            row = connection.execute(
                "SELECT tenant_id FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        tenant_id = row["tenant_id"] if row is not None else storage.DEFAULT_TENANT_ID
        return replace(device, tenant_id=tenant_id), token

    def list_for_user(self, user_id: str) -> list[Device]:
        """The sessions an account can see and revoke — its own, only."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT " + _DEVICE_COLUMNS + _DEVICE_SOURCE
                + " WHERE d.user_id = ? ORDER BY d.created_at DESC",
                (user_id,),
            ).fetchall()
        return [device for device in map(self._from_row, rows) if device is not None]

    def revoke(self, device_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

    def revoke_for_user(self, user_id: str, keep_device_id: str | None = None) -> int:
        """Sign an account out everywhere — used after a password change."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM devices WHERE user_id = ? AND device_id IS NOT ?",
                (user_id, keep_device_id),
            )
        return cursor.rowcount

    def find_by_id(self, device_id: str) -> Device | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT " + _DEVICE_COLUMNS + _DEVICE_SOURCE + " WHERE d.device_id = ?",
                (device_id,),
            ).fetchone()
        return self._from_row(row)

    def authenticate(self, token: str, max_age_seconds: int | None = None) -> Device | None:
        token_hash = self._hash_token(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT " + _DEVICE_COLUMNS + ", d.created_at" + _DEVICE_SOURCE
                + " WHERE d.token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        if max_age_seconds is not None and self._expired(row["created_at"], max_age_seconds):
            self.revoke(row["device_id"])
            return None
        return self._from_row(row)

    @staticmethod
    def _expired(created_at: str, max_age_seconds: int) -> bool:
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            return True
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > timedelta(seconds=max_age_seconds)

    @staticmethod
    def _from_row(row: sqlite3.Row | None) -> Device | None:
        if row is None:
            return None
        keys = row.keys()
        return Device(
            device_id=row["device_id"],
            name=row["name"],
            token_hash=row["token_hash"],
            user_id=row["user_id"] if "user_id" in keys else storage.DEFAULT_USER_ID,
            tenant_id=(
                row["tenant_id"] if "tenant_id" in keys and row["tenant_id"]
                else storage.DEFAULT_TENANT_ID
            ),
        )
