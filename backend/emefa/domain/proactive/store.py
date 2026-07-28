"""Initiative persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from emefa.domain import storage
from emefa.domain.policy import ActionRisk
from emefa.domain.proactive.schemas import (
    CLOSED_STATUSES,
    AutonomyLevel,
    Initiative,
    InitiativeStatus,
    InitiativeType,
)

_COLUMNS = (
    "initiative_id, type, title, reason, next_action, autonomy_level, risk, "
    "status, dedupe_key, cost_max_tokens, deadline, payload, created_at, resolved_at"
)

OPEN_STATUSES = ("pending", "approved", "executing")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InitiativeRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    def raise_initiative(self, initiative: Initiative) -> Initiative | None:
        """Record a new initiative, or return None if the same concern is
        already open.

        Deduplication is enforced by the database, not by a prior SELECT: two
        collectors running concurrently would both pass the check and both
        insert. Letting the unique index refuse the second is the only version
        that is actually correct.
        """
        with self._connect() as connection:
            try:
                connection.execute(
                    f"INSERT INTO initiatives ({_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        initiative.initiative_id,
                        initiative.type.value,
                        initiative.title,
                        initiative.reason,
                        initiative.next_action,
                        int(initiative.autonomy_level),
                        initiative.risk.value,
                        initiative.status.value,
                        initiative.dedupe_key,
                        initiative.cost_max_tokens,
                        initiative.deadline,
                        json.dumps(initiative.payload, ensure_ascii=False),
                        initiative.created_at,
                        initiative.resolved_at,
                    ),
                )
            except sqlite3.IntegrityError:
                return None
        return initiative

    def get(self, initiative_id: str) -> Initiative | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM initiatives WHERE initiative_id = ?",
                (initiative_id,),
            ).fetchone()
        return _from_row(row) if row is not None else None

    def open_initiatives(self, limit: int = 50) -> list[Initiative]:
        placeholders = ",".join("?" * len(OPEN_STATUSES))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM initiatives WHERE status IN ({placeholders}) "
                "ORDER BY created_at DESC LIMIT ?",
                (*OPEN_STATUSES, limit),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def history(self, limit: int = 50) -> list[Initiative]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM initiatives ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def set_status(self, initiative_id: str, status: InitiativeStatus) -> Initiative | None:
        resolved = _now() if status in CLOSED_STATUSES else None
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE initiatives SET status = ?, resolved_at = ? WHERE initiative_id = ?",
                (status.value, resolved, initiative_id),
            ).rowcount
        return self.get(initiative_id) if updated else None

    def expire_overdue(self, now: str | None = None) -> int:
        """Close initiatives whose deadline has passed.

        An initiative that outlives its own deadline is worse than none: it
        tells the user something is still pending when the moment to act has
        gone.
        """
        reference = now or _now()
        placeholders = ",".join("?" * len(OPEN_STATUSES))
        with self._connect() as connection:
            expired = connection.execute(
                f"UPDATE initiatives SET status = ?, resolved_at = ? "
                f"WHERE status IN ({placeholders}) AND deadline IS NOT NULL "
                "AND deadline < ?",
                (InitiativeStatus.EXPIRED.value, reference, *OPEN_STATUSES, reference),
            ).rowcount
        return int(expired)

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM initiatives GROUP BY status"
            ).fetchall()
        return {row["status"]: int(row["total"]) for row in rows}


def new_initiative_id() -> str:
    return f"ini_{uuid.uuid4().hex[:12]}"


def _from_row(row: sqlite3.Row) -> Initiative:
    return Initiative(
        initiative_id=row["initiative_id"],
        type=InitiativeType(row["type"]),
        title=row["title"],
        reason=row["reason"],
        next_action=row["next_action"],
        autonomy_level=AutonomyLevel(int(row["autonomy_level"])),
        risk=ActionRisk(row["risk"]),
        status=InitiativeStatus(row["status"]),
        dedupe_key=row["dedupe_key"],
        cost_max_tokens=row["cost_max_tokens"],
        deadline=row["deadline"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
        payload=json.loads(row["payload"] or "{}"),
    )
