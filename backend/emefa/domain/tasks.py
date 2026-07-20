"""Tasks and commitments persistence (single-tenant mode)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from emefa.domain import storage


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    title: str
    details: str
    due_date: str | None
    status: str
    created_at: str
    completed_at: str | None

    def bucket(self, today: date | None = None) -> str:
        if self.status != "open":
            return self.status
        if not self.due_date:
            return "sans_echeance"
        current = today or date.today()
        try:
            due = date.fromisoformat(self.due_date)
        except ValueError:
            return "sans_echeance"
        if due < current:
            return "en_retard"
        if due == current:
            return "aujourdhui"
        return "a_venir"


_COLUMNS = "task_id, title, details, due_date, status, created_at, completed_at"


class TaskRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def create(self, title: str, details: str = "", due_date: str | None = None) -> Task:
        cleaned_due = due_date or None
        if cleaned_due is not None:
            date.fromisoformat(cleaned_due)  # validate; raises ValueError
        task_id = uuid.uuid4().hex
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO tasks (task_id, title, details, due_date) VALUES (?, ?, ?, ?)",
                (task_id, title.strip(), details.strip(), cleaned_due),
            )
        found = self.get(task_id)
        assert found is not None
        return found

    def get(self, task_id: str) -> Task | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return Task(**dict(row)) if row is not None else None

    def list_open(self, limit: int = 50) -> list[Task]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE status = 'open' "
                "ORDER BY due_date IS NULL, due_date, created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [Task(**dict(row)) for row in rows]

    def complete(self, task_id: str) -> Task | None:
        with storage.connect(self.database_path) as connection:
            updated = connection.execute(
                "UPDATE tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP "
                "WHERE task_id = ? AND status = 'open'",
                (task_id,),
            ).rowcount
        return self.get(task_id) if updated else None
