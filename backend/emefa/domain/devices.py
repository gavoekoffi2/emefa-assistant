"""Device identity and token persistence."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


@dataclass(frozen=True, slots=True)
class Device:
    device_id: str
    name: str
    token_hash: str


class DeviceRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            current = int(row[0]) if row is not None and row[0] is not None else 0
            for version, statement in enumerate(MIGRATIONS[current:], start=current + 1):
                connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )

    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0]) if row is not None and row[0] is not None else 0

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
                "SELECT device_id, name, token_hash FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return self._from_row(row)

    def authenticate(self, token: str, max_age_seconds: int | None = None) -> Device | None:
        token_hash = self._hash_token(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT device_id, name, token_hash, created_at FROM devices WHERE token_hash = ?",
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
        return Device(
            device_id=row["device_id"],
            name=row["name"],
            token_hash=row["token_hash"],
        )
