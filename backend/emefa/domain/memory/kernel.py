"""SQLite access layer for the memory kernel — the single source of truth.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

Three invariants hold everywhere in this module:

1. **An event is never deleted.** It is the provenance of every fact.
2. **A contradicted fact is never deleted.** It becomes `superseded` and is
   linked to whatever replaced it, so "you told me X, now it's Y" stays
   answerable. The only path that removes rows is `forget()`, which exists
   because the user is entitled to be forgotten (CLAUDE.md §26).
3. **Re-observing a fact does not duplicate it.** It appends an observation
   and raises confidence. This is the difference between a memory that
   sharpens with use and one that silts up.

Scope columns are written on every row from day one. Values are constant
while ADR-001 single-tenant mode holds, but no query runs without them.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.memory import vocabulary
from emefa.domain.memory.schemas import (
    INITIAL_CONFIDENCE,
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    REINFORCEMENT_STEP,
    WEAKENING_STEP,
    DecayPolicy,
    Fact,
    FactObservation,
    FactRelation,
    FactStatus,
    MemoryEvent,
    ObservationType,
    RelationType,
)

_FACT_COLUMNS = (
    "fact_id, subject, predicate, object, category, status, confidence, "
    "support_count, importance, decay_policy, source, source_event_id, "
    "created_at, last_seen_at, updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


class MemoryKernel:
    """Storage primitives. Policy (when to reinforce, when to supersede) lives
    one layer up in `emefa.domain.memories`; this class only enforces the
    invariants that must never be bypassed."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        storage.run_migrations(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = storage.connect(self.database_path)
        # The API process and the voice bridge both write. Without WAL plus a
        # busy timeout, a concurrent write fails outright with "database is
        # locked" instead of waiting its turn.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    # ── events ────────────────────────────────────────────────────────────

    def log_event(
        self,
        type: str,
        source: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            event_id=_identifier("evt"),
            type=type,
            source=source,
            content=content,
            created_at=_now(),
            metadata=metadata or {},
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memory_events "
                "(event_id, type, source, content, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.type,
                    event.source,
                    event.content,
                    json.dumps(event.metadata, ensure_ascii=False),
                    event.created_at,
                ),
            )
        return event

    def recent_events(self, limit: int = 50, since: str | None = None) -> list[MemoryEvent]:
        query = (
            "SELECT event_id, type, source, content, metadata, created_at "
            "FROM memory_events"
        )
        parameters: list[Any] = []
        if since is not None:
            query += " WHERE created_at >= ?"
            parameters.append(since)
        query += " ORDER BY created_at DESC, event_id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            MemoryEvent(
                event_id=row["event_id"],
                type=row["type"],
                source=row["source"],
                content=row["content"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"] or "{}"),
            )
            for row in rows
        ]

    def count_events(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0])

    # ── facts ─────────────────────────────────────────────────────────────

    def insert_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        category: str,
        *,
        source: str = "conversation",
        source_event_id: str | None = None,
        confidence: float = INITIAL_CONFIDENCE,
        fact_id: str | None = None,
    ) -> Fact:
        category = vocabulary.normalise_category(category)
        fact = Fact(
            fact_id=fact_id or _identifier("fct"),
            subject=vocabulary.normalise_term(subject) or vocabulary.DEFAULT_SUBJECT,
            predicate=vocabulary.normalise_predicate(predicate, category),
            object=" ".join(object.split()).strip(),
            category=category,
            status=FactStatus.ACTIVE,
            confidence=_clamp(confidence, MIN_CONFIDENCE, MAX_CONFIDENCE),
            support_count=1,
            importance=vocabulary.importance_for(category),
            decay_policy=vocabulary.decay_for(category),
            source=source,
            source_event_id=source_event_id,
            created_at=_now(),
            last_seen_at=_now(),
            updated_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO memory_facts ({_FACT_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact.fact_id,
                    fact.subject,
                    fact.predicate,
                    fact.object,
                    fact.category,
                    fact.status.value,
                    fact.confidence,
                    fact.support_count,
                    fact.importance,
                    fact.decay_policy.value,
                    fact.source,
                    fact.source_event_id,
                    fact.created_at,
                    fact.last_seen_at,
                    fact.updated_at,
                ),
            )
            self._index(connection, fact)
            self._observe(
                connection,
                fact.fact_id,
                source_event_id,
                ObservationType.CREATED,
                0.0,
            )
        return fact

    def get_fact(self, fact_id: str) -> Fact | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
        return _row_to_fact(row) if row is not None else None

    def find_active_match(self, subject: str, predicate: str, category: str) -> Fact | None:
        """The fact this claim would be a restatement of, if any.

        Matching on `(subject, predicate, category)` and not on the object is
        deliberate: it is exactly what lets a *changed* value be recognised as
        a contradiction of the old one rather than filed as an unrelated fact.
        """
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts "
                "WHERE subject = ? AND predicate = ? AND category = ? AND status = ? "
                "ORDER BY last_seen_at DESC LIMIT 1",
                (
                    vocabulary.normalise_term(subject),
                    predicate,
                    vocabulary.normalise_category(category),
                    FactStatus.ACTIVE.value,
                ),
            ).fetchone()
        return _row_to_fact(row) if row is not None else None

    def list_facts(
        self,
        status: FactStatus | None = FactStatus.ACTIVE,
        category: str | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        query = f"SELECT {_FACT_COLUMNS} FROM memory_facts"
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if category is not None:
            clauses.append("category = ?")
            parameters.append(vocabulary.normalise_category(category))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY last_seen_at DESC, fact_id LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_fact(row) for row in rows]

    def count_facts(self, status: FactStatus | None = FactStatus.ACTIVE) -> int:
        with self._connect() as connection:
            if status is None:
                row = connection.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM memory_facts WHERE status = ?", (status.value,)
                ).fetchone()
        return int(row[0])

    def reinforce(self, fact_id: str, event_id: str | None = None) -> Fact | None:
        """Record that a known fact was heard again. No new row."""
        fact = self.get_fact(fact_id)
        if fact is None:
            return None
        confidence = _clamp(
            fact.confidence + REINFORCEMENT_STEP, MIN_CONFIDENCE, MAX_CONFIDENCE
        )
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE memory_facts SET confidence = ?, support_count = support_count + 1, "
                "last_seen_at = ?, updated_at = ? WHERE fact_id = ?",
                (confidence, now, now, fact_id),
            )
            self._observe(
                connection,
                fact_id,
                event_id,
                ObservationType.REINFORCED,
                REINFORCEMENT_STEP,
            )
        return self.get_fact(fact_id)

    def supersede(
        self,
        old_fact_id: str,
        new_fact: Fact,
        event_id: str | None = None,
    ) -> Fact | None:
        """Mark a fact replaced by a newer one and link the two.

        The old row survives with `status='superseded'`. That is the whole
        point: the assistant keeps the ability to notice and mention that
        something changed.
        """
        old = self.get_fact(old_fact_id)
        if old is None:
            return None
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE memory_facts SET status = ?, confidence = ?, updated_at = ? "
                "WHERE fact_id = ?",
                (
                    FactStatus.SUPERSEDED.value,
                    _clamp(old.confidence - WEAKENING_STEP, MIN_CONFIDENCE, MAX_CONFIDENCE),
                    now,
                    old_fact_id,
                ),
            )
            self._observe(
                connection,
                old_fact_id,
                event_id,
                ObservationType.SUPERSEDED,
                -WEAKENING_STEP,
            )
            connection.execute(
                "INSERT INTO memory_fact_relations "
                "(relation_id, from_fact_id, to_fact_id, relation_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    _identifier("rel"),
                    new_fact.fact_id,
                    old_fact_id,
                    RelationType.SUPERSEDES.value,
                    now,
                ),
            )
        return self.get_fact(old_fact_id)

    def correct(self, fact_id: str, new_object: str, event_id: str | None = None) -> Fact | None:
        """Apply a human correction in place.

        Distinct from supersession: the user is not changing their mind, they
        are telling us we recorded it wrong. There is no earlier truth worth
        preserving, so the object is rewritten and confidence jumps — a human
        correction is the strongest evidence available.
        """
        fact = self.get_fact(fact_id)
        if fact is None:
            return None
        cleaned = " ".join(new_object.split()).strip()
        if not cleaned:
            raise ValueError("correction must not be empty")
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE memory_facts SET object = ?, confidence = ?, last_seen_at = ?, "
                "updated_at = ?, source = 'human_correction' WHERE fact_id = ?",
                (cleaned, MAX_CONFIDENCE, now, now, fact_id),
            )
            self._observe(
                connection, fact_id, event_id, ObservationType.CORRECTED, MAX_CONFIDENCE
            )
            connection.execute("DELETE FROM memory_facts_fts WHERE fact_id = ?", (fact_id,))
            updated = _row_to_fact(
                connection.execute(
                    f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id = ?", (fact_id,)
                ).fetchone()
            )
            self._index(connection, updated)
        return self.get_fact(fact_id)

    def forget(self, fact_id: str) -> bool:
        """Hard-delete a fact at the user's request — the one exception to the
        never-delete rule, required by CLAUDE.md §26. Observations and
        relations go with it; the originating events stay, because they are the
        record of the conversation, not of the belief."""
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM memory_facts WHERE fact_id = ?", (fact_id,)
            ).rowcount
            if deleted:
                connection.execute(
                    "DELETE FROM memory_fact_observations WHERE fact_id = ?", (fact_id,)
                )
                connection.execute(
                    "DELETE FROM memory_fact_relations "
                    "WHERE from_fact_id = ? OR to_fact_id = ?",
                    (fact_id, fact_id),
                )
                connection.execute(
                    "DELETE FROM memory_facts_fts WHERE fact_id = ?", (fact_id,)
                )
        return bool(deleted)

    # ── search ────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> list[tuple[Fact, float]]:
        """Full-text candidates with their raw BM25 score (lower is better).

        Returns nothing rather than raising when the query has no usable
        tokens — punctuation-only input is a normal thing for a voice
        transcript to produce.
        """
        match = _fts_query(query)
        if not match:
            return []
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    "SELECT f.fact_id, bm25(memory_facts_fts) AS rank "
                    "FROM memory_facts_fts f "
                    "WHERE memory_facts_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (match, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                # Malformed MATCH expression from unusual input; degrade to no
                # text hits rather than failing the user's turn.
                return []
            if not rows:
                return []
            ranks = {row["fact_id"]: float(row["rank"]) for row in rows}
            placeholders = ",".join("?" * len(ranks))
            facts = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts "
                f"WHERE fact_id IN ({placeholders})",
                tuple(ranks),
            ).fetchall()
        return [(_row_to_fact(row), ranks[row["fact_id"]]) for row in facts]

    # ── observations and relations ────────────────────────────────────────

    def list_observations(self, fact_id: str) -> list[FactObservation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT observation_id, fact_id, event_id, observation_type, "
                "confidence_delta, created_at FROM memory_fact_observations "
                "WHERE fact_id = ? ORDER BY created_at",
                (fact_id,),
            ).fetchall()
        return [
            FactObservation(
                observation_id=row["observation_id"],
                fact_id=row["fact_id"],
                event_id=row["event_id"],
                observation_type=ObservationType(row["observation_type"]),
                confidence_delta=float(row["confidence_delta"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def link(
        self, from_fact_id: str, to_fact_id: str, relation_type: RelationType
    ) -> FactRelation:
        relation = FactRelation(
            relation_id=_identifier("rel"),
            from_fact_id=from_fact_id,
            to_fact_id=to_fact_id,
            relation_type=relation_type,
            created_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memory_fact_relations "
                "(relation_id, from_fact_id, to_fact_id, relation_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    relation.relation_id,
                    relation.from_fact_id,
                    relation.to_fact_id,
                    relation.relation_type.value,
                    relation.created_at,
                ),
            )
        return relation

    def superseded_by(self, fact_id: str) -> list[Fact]:
        """Facts this one replaced — what the user used to believe."""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id IN ("
                "  SELECT to_fact_id FROM memory_fact_relations "
                "  WHERE from_fact_id = ? AND relation_type = ?"
                ")",
                (fact_id, RelationType.SUPERSEDES.value),
            ).fetchall()
        return [_row_to_fact(row) for row in rows]

    # ── internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _index(connection: sqlite3.Connection, fact: Fact) -> None:
        connection.execute(
            "INSERT INTO memory_facts_fts (fact_id, text) VALUES (?, ?)",
            (fact.fact_id, fact.search_text()),
        )

    @staticmethod
    def _observe(
        connection: sqlite3.Connection,
        fact_id: str,
        event_id: str | None,
        observation_type: ObservationType,
        delta: float,
    ) -> None:
        connection.execute(
            "INSERT INTO memory_fact_observations "
            "(observation_id, fact_id, event_id, observation_type, "
            "confidence_delta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _identifier("obs"),
                fact_id,
                event_id,
                observation_type.value,
                delta,
                _now(),
            ),
        )


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        fact_id=row["fact_id"],
        subject=row["subject"],
        predicate=row["predicate"],
        object=row["object"],
        category=row["category"],
        status=FactStatus(row["status"]),
        confidence=float(row["confidence"]),
        support_count=int(row["support_count"]),
        importance=float(row["importance"]),
        decay_policy=DecayPolicy(row["decay_policy"]),
        source=row["source"],
        source_event_id=row["source_event_id"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        updated_at=row["updated_at"],
    )


_FTS_SAFE = set("abcdefghijklmnopqrstuvwxyz0123456789àâäçéèêëîïôöùûüÿœæ ")


def _fts_query(query: str) -> str:
    """Turn free text into a safe FTS5 OR-query.

    User text reaches this straight from a chat box or a voice transcript, so
    it contains quotes, asterisks and `NEAR` — all FTS5 operators. Rather than
    escape the grammar, every token is reduced to bare word characters and
    re-quoted, which cannot express an operator at all.
    """
    lowered = query.lower()
    cleaned = "".join(character if character in _FTS_SAFE else " " for character in lowered)
    tokens = [token for token in cleaned.split() if len(token) > 2]
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens[:12])
