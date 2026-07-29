"""Tasks and commitments persistence (single-tenant mode)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from emefa.domain import storage
from emefa.domain.scope import Scope, ScopedStore


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


class TaskRepository(ScopedStore):
    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def create(self, title: str, details: str = "", due_date: str | None = None) -> Task:
        cleaned_due = due_date or None
        if cleaned_due is not None:
            date.fromisoformat(cleaned_due)  # validate; raises ValueError
        task_id = uuid.uuid4().hex
        self.insert("tasks", {
            "task_id": task_id, "title": title.strip(),
            "details": details.strip(), "due_date": cleaned_due,
        })
        found = self.get(task_id)
        assert found is not None
        return found

    def get(self, task_id: str) -> Task | None:
        row = self.fetch_one(_COLUMNS, "tasks", "task_id = ?", (task_id,))
        return Task(**row) if row is not None else None

    def list_open(self, limit: int = 50) -> list[Task]:
        rows = self.fetch_all(
            _COLUMNS, "tasks", "status = 'open'", (limit,),
            "ORDER BY due_date IS NULL, due_date, created_at LIMIT ?",
        )
        return [Task(**row) for row in rows]

    def list_completed_since(self, since: str, limit: int = 50) -> list[Task]:
        """Tasks closed on or after ``since`` (YYYY-MM-DD) — evening report."""
        rows = self.fetch_all(
            _COLUMNS, "tasks", "status = 'done' AND completed_at >= ?", (since, limit),
            "ORDER BY completed_at DESC LIMIT ?",
        )
        return [Task(**row) for row in rows]

    def complete(self, task_id: str) -> Task | None:
        with storage.connect(self.database_path) as connection:
            updated = connection.execute(
                "UPDATE tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP "
                f"WHERE task_id = ? AND status = 'open' AND {self.scope.predicate}",
                (task_id, *self.scope.values),
            ).rowcount
        return self.get(task_id) if updated else None
