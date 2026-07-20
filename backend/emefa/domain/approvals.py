"""Persistence for consequential actions awaiting user approval."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.agent import RequestedAction


@dataclass(frozen=True, slots=True)
class PendingAction:
    action_id: str
    conversation_id: str
    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None
    status: str
    created_at: str

    def to_requested_action(self) -> RequestedAction:
        return RequestedAction(
            name=self.tool_name, arguments=dict(self.arguments), call_id=self.call_id
        )


class ApprovalRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def create(self, conversation_id: str, action: RequestedAction) -> PendingAction:
        action_id = uuid.uuid4().hex
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO pending_actions "
                "(action_id, conversation_id, tool_name, arguments, call_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    action_id,
                    conversation_id,
                    action.name,
                    json.dumps(action.arguments, ensure_ascii=False),
                    action.call_id,
                ),
            )
        found = self.get(action_id)
        assert found is not None
        return found

    def get(self, action_id: str) -> PendingAction | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT action_id, conversation_id, tool_name, arguments, call_id, "
                "status, created_at FROM pending_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return self._from_row(row)

    def pending_for(self, conversation_id: str) -> list[PendingAction]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT action_id, conversation_id, tool_name, arguments, call_id, "
                "status, created_at FROM pending_actions "
                "WHERE conversation_id = ? AND status = 'pending' ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        return [action for row in rows if (action := self._from_row(row)) is not None]

    def resolve(self, action_id: str, status: str) -> None:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE pending_actions SET status = ?, resolved_at = CURRENT_TIMESTAMP "
                "WHERE action_id = ?",
                (status, action_id),
            )

    @staticmethod
    def _from_row(row) -> PendingAction | None:
        if row is None:
            return None
        return PendingAction(
            action_id=row["action_id"],
            conversation_id=row["conversation_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments"]),
            call_id=row["call_id"],
            status=row["status"],
            created_at=row["created_at"],
        )
