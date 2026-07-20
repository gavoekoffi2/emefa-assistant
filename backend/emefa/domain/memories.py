"""Durable, user-controllable memory (Phase 4 MVP).

Structured entries with provenance — not raw chat storage. The context
block injected into the brain is bounded in both entry count and entry
length so memory can never crowd out the conversation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from emefa.domain import storage

CATEGORIES = ("fact", "preference", "relationship", "procedure", "other")
_COLUMNS = "memory_id, category, content, source, created_at"


@dataclass(frozen=True, slots=True)
class Memory:
    memory_id: str
    category: str
    content: str
    source: str
    created_at: str


class MemoryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def remember(
        self, content: str, category: str = "fact", source: str = "conversation"
    ) -> Memory:
        cleaned = " ".join(content.split()).strip()[:500]
        if not cleaned:
            raise ValueError("memory content must not be empty")
        if category not in CATEGORIES:
            category = "other"
        memory_id = uuid.uuid4().hex
        with storage.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO memories (memory_id, category, content, source) "
                "VALUES (?, ?, ?, ?)",
                (memory_id, category, cleaned, source),
            )
        found = self.get(memory_id)
        assert found is not None
        return found

    def get(self, memory_id: str) -> Memory | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        return Memory(**dict(row)) if row is not None else None

    def list_all(self, limit: int = 100) -> list[Memory]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM memories ORDER BY created_at DESC, memory_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [Memory(**dict(row)) for row in rows]

    def forget(self, memory_id: str) -> bool:
        with storage.connect(self.database_path) as connection:
            deleted = connection.execute(
                "DELETE FROM memories WHERE memory_id = ?", (memory_id,)
            ).rowcount
        return bool(deleted)

    def context_block(self, max_items: int = 12, max_chars: int = 200) -> str:
        """Bounded memory block for the system prompt; empty string when no memory."""
        entries = self.list_all(limit=max_items)
        if not entries:
            return ""
        lines = ["Mémoire durable (l'utilisateur peut la consulter et l'effacer) :"]
        lines.extend(f"- [{entry.category}] {entry.content[:max_chars]}" for entry in entries)
        return "\n".join(lines)
