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

from emefa.domain import storage

_TABLES = {"briefings", "evening_reports"}


@dataclass(frozen=True, slots=True)
class Briefing:
    brief_date: str
    content: dict[str, Any]
    emailed: bool
    created_at: str


class BriefingRepository:
    def __init__(self, database_path: Path, table: str = "briefings") -> None:
        if table not in _TABLES:
            raise ValueError(f"unknown report table: {table}")
        self.database_path = database_path
        self.table = table
        storage.run_migrations(database_path)

    def save(self, brief_date: str, content: dict[str, Any]) -> Briefing:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"INSERT INTO {self.table} (brief_date, content) VALUES (?, ?) "
                "ON CONFLICT(brief_date) DO UPDATE SET content = excluded.content",
                (brief_date, json.dumps(content, ensure_ascii=False)),
            )
        found = self.get(brief_date)
        assert found is not None
        return found

    def get(self, brief_date: str) -> Briefing | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT brief_date, content, emailed, created_at "
                f"FROM {self.table} WHERE brief_date = ?",
                (brief_date,),
            ).fetchone()
        if row is None:
            return None
        return Briefing(
            brief_date=row["brief_date"],
            content=json.loads(row["content"]),
            emailed=bool(row["emailed"]),
            created_at=row["created_at"],
        )

    def mark_emailed(self, brief_date: str) -> None:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"UPDATE {self.table} SET emailed = 1 WHERE brief_date = ?", (brief_date,)
            )
