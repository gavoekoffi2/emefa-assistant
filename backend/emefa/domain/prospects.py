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

from emefa.domain.scope import Ownership, Scope, ScopedStore

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


class ProspectRepository(ScopedStore):
    """The legacy pipeline. Belongs to the company, like the CRM it precedes."""

    ownership = Ownership.TENANT

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def add(self, name: str, **fields: Any) -> Prospect:
        cleaned_name = " ".join(str(name).split())[:200]
        if not cleaned_name:
            raise ValueError("prospect name must not be empty")
        values = self._clean_fields(fields)
        prospect_id = uuid.uuid4().hex
        self.insert("prospects", {"prospect_id": prospect_id, "name": cleaned_name, **values})
        found = self.get(prospect_id)
        assert found is not None
        return found

    def get(self, prospect_id: str) -> Prospect | None:
        row = self.fetch_one(_COLUMNS, "prospects", "prospect_id = ?", (prospect_id,))
        return Prospect(**row) if row is not None else None

    def list_open(self, limit: int = 100) -> list[Prospect]:
        rows = self.fetch_all(
            _COLUMNS, "prospects",
            f"stage IN ({', '.join('?' for _ in OPEN_STAGES)})", (*OPEN_STAGES, limit),
            "ORDER BY next_action_date IS NULL, next_action_date, created_at LIMIT ?",
        )
        return [Prospect(**row) for row in rows]

    def update(self, prospect_id: str, **fields: Any) -> Prospect | None:
        if self.get(prospect_id) is None:
            return None
        values = self._clean_fields(fields)
        stage = fields.get("stage")
        if isinstance(stage, str) and stage in STAGES:
            values["stage"] = stage
        if not values:
            return self.get(prospect_id)
        self.update_scoped("prospects", "prospect_id", prospect_id, values)
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
