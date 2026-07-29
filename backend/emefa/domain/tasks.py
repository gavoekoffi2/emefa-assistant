"""Tasks and commitments persistence (single-tenant mode)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    title: str
    details: str
    due_date: str | None
    status: str
    created_at: str
    completed_at: str | None
    #: ``None`` means the company has not given it to anybody yet.
    assigned_to_user_id: str | None = None

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


_COLUMNS = (
    "task_id, title, details, due_date, status, created_at, completed_at, "
    "assigned_to_user_id"
)


class TaskRepository(ScopedStore):
    """Commitments belong to the company; each one may have an assignee.

    ``list_open`` is the company view. ``list_mine`` is what a briefing shows:
    what I was assigned, plus anything nobody has taken.
    """

    ownership = Ownership.TENANT

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def create(
        self,
        title: str,
        details: str = "",
        due_date: str | None = None,
        assigned_to_user_id: str | None = None,
    ) -> Task:
        cleaned_due = due_date or None
        if cleaned_due is not None:
            date.fromisoformat(cleaned_due)  # validate; raises ValueError
        task_id = uuid.uuid4().hex
        # A task EMEFA creates while talking to someone is theirs by default.
        self.insert("tasks", {
            "task_id": task_id, "title": title.strip(),
            "details": details.strip(), "due_date": cleaned_due,
            "assigned_to_user_id": assigned_to_user_id or self.scope.user_id,
        })
        found = self.get(task_id)
        assert found is not None
        return found

    def get(self, task_id: str) -> Task | None:
        row = self.fetch_one(_COLUMNS, "tasks", "task_id = ?", (task_id,))
        return Task(**row) if row is not None else None

    def list_open(self, limit: int = 50) -> list[Task]:
        """Every open commitment in the company."""
        rows = self.fetch_all(
            _COLUMNS, "tasks", "status = 'open'", (limit,),
            "ORDER BY due_date IS NULL, due_date, created_at LIMIT ?",
        )
        return [Task(**row) for row in rows]

    def list_mine(self, limit: int = 50) -> list[Task]:
        """What a briefing shows: mine, plus what nobody has taken."""
        rows = self.fetch_all(
            _COLUMNS, "tasks",
            "status = 'open' AND (assigned_to_user_id = ? OR assigned_to_user_id IS NULL)",
            (self.scope.user_id, limit),
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
                f"WHERE task_id = ? AND status = 'open' "
                f"AND {self.scope.predicate(self.ownership)}",
                (task_id, *self.scope.values(self.ownership)),
            ).rowcount
        return self.get(task_id) if updated else None
