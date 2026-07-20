"""Stored proactive daily briefings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain import storage


@dataclass(frozen=True, slots=True)
class Briefing:
    brief_date: str
    content: dict[str, Any]
    emailed: bool
    created_at: str


class BriefingRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def save(self, brief_date: str, content: dict[str, Any]) -> Briefing:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO briefings (brief_date, content) VALUES (?, ?) "
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
                "FROM briefings WHERE brief_date = ?",
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
                "UPDATE briefings SET emailed = 1 WHERE brief_date = ?", (brief_date,)
            )
