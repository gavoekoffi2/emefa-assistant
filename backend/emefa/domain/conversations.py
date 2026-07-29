"""Durable conversation history for the EMEFA runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from emefa.domain.scope import Ownership, Scope, ScopedStore

# Single-user voice channel; the ElevenLabs bridge has no device binding.
VOICE_CONVERSATION_ID = "voice:default"


class ConversationStore(ScopedStore):
    """What was said to EMEFA, by one person, inside their company."""

    ownership = Ownership.USER

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def recent(self, conversation_id: str, limit: int = 12) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            "payload", "conversation_turns", "conversation_id = ?", (conversation_id, limit),
            "ORDER BY turn_id DESC LIMIT ?",
        )
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def extend(self, conversation_id: str, entries: Sequence[Mapping[str, Any]]) -> None:
        if not entries:
            return
        for entry in entries:
            self.insert("conversation_turns", {
                "conversation_id": conversation_id,
                "payload": json.dumps(dict(entry), ensure_ascii=False),
            })

    def forget(self, conversation_id: str) -> None:
        self.delete_scoped("conversation_turns", "conversation_id", conversation_id)
