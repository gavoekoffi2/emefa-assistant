"""Device identity and token persistence."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
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

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM devices").fetchone()
        return int(row[0]) if row is not None else 0

    def enroll(self, name: str) -> tuple[Device, str]:
        token = secrets.token_urlsafe(32)
        device = Device(
            device_id=str(uuid.uuid4()),
            name=name,
            token_hash=self._hash_token(token),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO devices (device_id, name, token_hash) VALUES (?, ?, ?)",
                (device.device_id, device.name, device.token_hash),
            )
        return device, token

    def revoke(self, device_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))

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
