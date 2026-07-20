"""Durable conversation history for the EMEFA runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from emefa.domain import storage


class ConversationStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def recent(self, conversation_id: str, limit: int = 12) -> list[dict[str, Any]]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT payload FROM conversation_turns WHERE conversation_id = ? "
                "ORDER BY turn_id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def extend(self, conversation_id: str, entries: Sequence[Mapping[str, Any]]) -> None:
        if not entries:
            return
        with storage.connect(self.database_path) as connection:
            connection.executemany(
                "INSERT INTO conversation_turns (conversation_id, payload) VALUES (?, ?)",
                [
                    (conversation_id, json.dumps(dict(entry), ensure_ascii=False))
                    for entry in entries
                ],
            )

    def forget(self, conversation_id: str) -> None:
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "DELETE FROM conversation_turns WHERE conversation_id = ?",
                (conversation_id,),
            )
