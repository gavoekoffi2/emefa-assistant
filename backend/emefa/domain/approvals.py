"""Persistence for consequential actions awaiting user approval."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore
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


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


_COLUMNS = (
    "action_id, conversation_id, tool_name, arguments, call_id, status, created_at"
)


class ApprovalRepository(ScopedStore):
    """A consequential action waiting for its owner's explicit yes."""

    ownership = Ownership.USER

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def create(self, conversation_id: str, action: RequestedAction) -> PendingAction:
        action_id = uuid.uuid4().hex
        self.insert("pending_actions", {
            "action_id": action_id, "conversation_id": conversation_id,
            "tool_name": action.name,
            "arguments": json.dumps(action.arguments, ensure_ascii=False),
            "call_id": action.call_id,
        })
        found = self.get(action_id)
        assert found is not None
        return found

    def get(self, action_id: str) -> PendingAction | None:
        return self._from_row(
            self.fetch_one(_COLUMNS, "pending_actions", "action_id = ?", (action_id,))
        )

    def pending_for(self, conversation_id: str) -> list[PendingAction]:
        rows = self.fetch_all(
            _COLUMNS, "pending_actions", "conversation_id = ? AND status = 'pending'",
            (conversation_id,), "ORDER BY created_at",
        )
        return [action for row in rows if (action := self._from_row(row)) is not None]

    def claim(self, action_id: str) -> bool:
        """Atomically reserve a pending action before executing its side effect."""
        # Still one statement, so two concurrent approvals cannot both win.
        with storage.connect(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE pending_actions SET status = 'executing' "
                f"WHERE action_id = ? AND status = 'pending' "
                f"AND {self.scope.predicate(self.ownership)}",
                (action_id, *self.scope.values(self.ownership)),
            )
            return cursor.rowcount == 1

    def resolve(self, action_id: str, status: str) -> None:
        self.update_scoped(
            "pending_actions", "action_id", action_id,
            {"status": status, "resolved_at": _now()}, touch_updated_at=False,
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
