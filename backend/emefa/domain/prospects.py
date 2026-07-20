"""Local sales-pipeline persistence (business development seed).

Pipeline tracking only: prospect discovery/enrichment will come later
through vetted external providers. No outreach happens here — sending
anything remains a COMMUNICATE action behind user approval.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from emefa.domain import storage

STAGES = ("nouveau", "contacté", "qualifié", "proposition", "gagné", "perdu")
OPEN_STAGES = ("nouveau", "contacté", "qualifié", "proposition")
_COLUMNS = (
    "prospect_id, name, company, email, phone, stage, notes, "
    "next_action, next_action_date, created_at, updated_at"
)
_EDITABLE_FIELDS = ("name", "company", "email", "phone", "notes", "next_action")


@dataclass(frozen=True, slots=True)
class Prospect:
    prospect_id: str
    name: str
    company: str
    email: str
    phone: str
    stage: str
    notes: str
    next_action: str
    next_action_date: str | None
    created_at: str
    updated_at: str

    def follow_up_due(self, today: date | None = None) -> bool:
        if self.stage not in OPEN_STAGES or not self.next_action_date:
            return False
        try:
            return date.fromisoformat(self.next_action_date) <= (today or date.today())
        except ValueError:
            return False


class ProspectRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def add(self, name: str, **fields: Any) -> Prospect:
        cleaned_name = " ".join(str(name).split())[:200]
        if not cleaned_name:
            raise ValueError("prospect name must not be empty")
        values = self._clean_fields(fields)
        prospect_id = uuid.uuid4().hex
        columns = ["prospect_id", "name", *values.keys()]
        placeholders = ", ".join("?" for _ in columns)
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"INSERT INTO prospects ({', '.join(columns)}) VALUES ({placeholders})",
                (prospect_id, cleaned_name, *values.values()),
            )
        found = self.get(prospect_id)
        assert found is not None
        return found

    def get(self, prospect_id: str) -> Prospect | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM prospects WHERE prospect_id = ?",
                (prospect_id,),
            ).fetchone()
        return Prospect(**dict(row)) if row is not None else None

    def list_open(self, limit: int = 100) -> list[Prospect]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM prospects "
                f"WHERE stage IN ({', '.join('?' for _ in OPEN_STAGES)}) "
                "ORDER BY next_action_date IS NULL, next_action_date, created_at LIMIT ?",
                (*OPEN_STAGES, limit),
            ).fetchall()
        return [Prospect(**dict(row)) for row in rows]

    def update(self, prospect_id: str, **fields: Any) -> Prospect | None:
        if self.get(prospect_id) is None:
            return None
        values = self._clean_fields(fields)
        stage = fields.get("stage")
        if isinstance(stage, str) and stage in STAGES:
            values["stage"] = stage
        if not values:
            return self.get(prospect_id)
        assignments = ", ".join(f"{column} = ?" for column in values)
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"UPDATE prospects SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE prospect_id = ?",
                (*values.values(), prospect_id),
            )
        return self.get(prospect_id)

    def due_follow_ups(self, today: date | None = None) -> list[Prospect]:
        return [p for p in self.list_open() if p.follow_up_due(today)]

    @staticmethod
    def _clean_fields(fields: dict[str, Any]) -> dict[str, str | None]:
        values: dict[str, str | None] = {}
        for field in _EDITABLE_FIELDS:
            if field in fields and isinstance(fields[field], (str, int, float)):
                values[field] = str(fields[field]).strip()[:2_000]
        if "next_action_date" in fields:
            raw = fields["next_action_date"]
            if raw in (None, ""):
                values["next_action_date"] = None
            else:
                date.fromisoformat(str(raw))  # validates; raises ValueError
                values["next_action_date"] = str(raw)
        return values
