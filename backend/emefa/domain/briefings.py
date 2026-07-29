"""Stored proactive reports — the morning brief and the evening report.

Both use the same shape and the same idempotency rule (one row per day, sent
at most once), so the repository is parameterised by table rather than
duplicated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain.scope import Ownership, Scope, ScopedStore

_TABLES = {"briefings", "evening_reports"}


@dataclass(frozen=True, slots=True)
class Briefing:
    brief_date: str
    content: dict[str, Any]
    emailed: bool
    created_at: str


class BriefingRepository(ScopedStore):
    """A report is written for one person, so it is personal."""

    ownership = Ownership.USER

    def __init__(
        self,
        database_path: Path,
        table: str = "briefings",
        scope: Scope | None = None,
    ) -> None:
        if table not in _TABLES:
            raise ValueError(f"unknown report table: {table}")
        self.table = table
        super().__init__(database_path, scope)

    def for_scope(self, scope: Scope) -> "BriefingRepository":
        return BriefingRepository(self.database_path, self.table, scope)

    def save(self, brief_date: str, content: dict[str, Any]) -> Briefing:
        payload = json.dumps(content, ensure_ascii=False)
        if self.get(brief_date) is None:
            self.insert(self.table, {"brief_date": brief_date, "content": payload})
        else:
            self.update_scoped(
                self.table, "brief_date", brief_date, {"content": payload},
                touch_updated_at=False,
            )
        found = self.get(brief_date)
        assert found is not None
        return found

    def get(self, brief_date: str) -> Briefing | None:
        row = self.fetch_one(
            "brief_date, content, emailed, created_at", self.table,
            "brief_date = ?", (brief_date,),
        )
        if row is None:
            return None
        return Briefing(
            brief_date=row["brief_date"],
            content=json.loads(row["content"]),
            emailed=bool(row["emailed"]),
            created_at=row["created_at"],
        )

    def mark_emailed(self, brief_date: str) -> None:
        self.update_scoped(
            self.table, "brief_date", brief_date, {"emailed": 1}, touch_updated_at=False
        )
