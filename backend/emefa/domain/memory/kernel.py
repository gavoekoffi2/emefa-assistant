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
from emefa.domain.scope import Scope
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
    "entity_id, created_at, last_seen_at, updated_at"
)


def _now() -> str:
    # Microsecond precision, not seconds: the consolidation watermark is a
    # timestamp comparison, and at second precision a pass would re-read the
    # events written in the same second it completed.
    return datetime.now(timezone.utc).isoformat()


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


class MemoryKernel:
    """Storage primitives. Policy (when to reinforce, when to supersede) lives
    one layer up in `emefa.domain.memories`; this class only enforces the
    invariants that must never be bypassed."""

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        self.database_path = database_path
        self.scope = scope or Scope()
        storage.run_migrations(database_path)

    def for_scope(self, scope: Scope) -> "MemoryKernel":
        return type(self)(self.database_path, scope)

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
                "(event_id, tenant_id, user_id, type, source, content, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    self.scope.tenant_id,
                    self.scope.user_id,
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
            "FROM memory_events WHERE tenant_id = ? AND user_id = ?"
        )
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id]
        if since is not None:
            query += " AND created_at >= ?"
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

    def oldest_events_after(
        self, since: str, limit: int = 50, *, exclude_type: str | None = None
    ) -> list[MemoryEvent]:
        """Return the oldest pending events after a durable watermark.

        Consolidation must drain a backlog from the front. Selecting the newest
        ``limit`` rows and then advancing a watermark would permanently skip
        older rows whenever more than one pass worth of events accumulated.
        """
        query = (
            "SELECT event_id, type, source, content, metadata, created_at "
            "FROM memory_events WHERE tenant_id = ? AND user_id = ? AND created_at > ?"
        )
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id, since]
        if exclude_type is not None:
            query += " AND type != ?"
            parameters.append(exclude_type)
        query += " ORDER BY created_at ASC, event_id ASC LIMIT ?"
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

    def latest_event(self, event_type: str) -> MemoryEvent | None:
        """Return the latest event of one type without a shallow scan limit."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT event_id, type, source, content, metadata, created_at "
                "FROM memory_events WHERE tenant_id = ? AND user_id = ? AND type = ? "
                "ORDER BY created_at DESC, event_id DESC LIMIT 1",
                (self.scope.tenant_id, self.scope.user_id, event_type),
            ).fetchone()
        if row is None:
            return None
        return MemoryEvent(
            event_id=row["event_id"],
            type=row["type"],
            source=row["source"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def count_events(self) -> int:
        with self._connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM memory_events WHERE tenant_id = ? AND user_id = ?",
                (self.scope.tenant_id, self.scope.user_id),
            ).fetchone()[0])

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
        entity_id: str | None = None,
    ) -> Fact:
        if source_event_id is not None and not self._owns_event(source_event_id):
            source_event_id = None
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
            entity_id=entity_id,
            created_at=_now(),
            last_seen_at=_now(),
            updated_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO memory_facts (tenant_id, user_id, {_FACT_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.scope.tenant_id,
                    self.scope.user_id,
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
                    fact.entity_id,
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
                f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (fact_id, self.scope.tenant_id, self.scope.user_id),
            ).fetchone()
        return _row_to_fact(row) if row is not None else None

    def find_active_match(
        self,
        subject: str,
        predicate: str,
        category: str,
        entity_id: str | None = None,
    ) -> Fact | None:
        """The fact this claim would be a restatement of, if any.

        Matching on `(subject, predicate, category)` and not on the object is
        deliberate: it is exactly what lets a *changed* value be recognised as
        a contradiction of the old one rather than filed as an unrelated fact.

        The entity is part of the key, and must be: without it, the objective
        of one project would supersede the objective of another the moment
        both were recorded.
        """
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts "
                "WHERE tenant_id = ? AND user_id = ? "
                "AND subject = ? AND predicate = ? AND category = ? AND status = ? "
                "AND entity_id IS ? ORDER BY last_seen_at DESC LIMIT 1",
                (
                    self.scope.tenant_id,
                    self.scope.user_id,
                    vocabulary.normalise_term(subject),
                    predicate,
                    vocabulary.normalise_category(category),
                    FactStatus.ACTIVE.value,
                    entity_id,
                ),
            ).fetchone()
        return _row_to_fact(row) if row is not None else None

    def list_facts(
        self,
        status: FactStatus | None = FactStatus.ACTIVE,
        category: str | None = None,
        limit: int = 100,
        entity_id: str | None = None,
        personal_only: bool = False,
    ) -> list[Fact]:
        query = f"SELECT {_FACT_COLUMNS} FROM memory_facts"
        clauses: list[str] = ["tenant_id = ?", "user_id = ?"]
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id]
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if category is not None:
            clauses.append("category = ?")
            parameters.append(vocabulary.normalise_category(category))
        if entity_id is not None:
            clauses.append("entity_id = ?")
            parameters.append(entity_id)
        elif personal_only:
            # Business memory must not leak into a personal answer.
            clauses.append("entity_id IS NULL")
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
                row = connection.execute(
                    "SELECT COUNT(*) FROM memory_facts WHERE tenant_id = ? AND user_id = ?",
                    (self.scope.tenant_id, self.scope.user_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM memory_facts WHERE tenant_id = ? AND user_id = ? "
                    "AND status = ?",
                    (self.scope.tenant_id, self.scope.user_id, status.value),
                ).fetchone()
        return int(row[0])

    def reinforce(self, fact_id: str, event_id: str | None = None) -> Fact | None:
        """Record that a known fact was heard again. No new row."""
        if event_id is not None and not self._owns_event(event_id):
            event_id = None
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
                "last_seen_at = ?, updated_at = ? WHERE fact_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (confidence, now, now, fact_id, self.scope.tenant_id, self.scope.user_id),
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
        if event_id is not None and not self._owns_event(event_id):
            event_id = None
        old = self.get_fact(old_fact_id)
        if old is None:
            return None
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE memory_facts SET status = ?, confidence = ?, updated_at = ? "
                "WHERE fact_id = ? AND tenant_id = ? AND user_id = ?",
                (
                    FactStatus.SUPERSEDED.value,
                    _clamp(old.confidence - WEAKENING_STEP, MIN_CONFIDENCE, MAX_CONFIDENCE),
                    now,
                    old_fact_id,
                    self.scope.tenant_id,
                    self.scope.user_id,
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
        if event_id is not None and not self._owns_event(event_id):
            event_id = None
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
                "updated_at = ?, source = 'human_correction' WHERE fact_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (cleaned, MAX_CONFIDENCE, now, now, fact_id,
                 self.scope.tenant_id, self.scope.user_id),
            )
            self._observe(
                connection, fact_id, event_id, ObservationType.CORRECTED, MAX_CONFIDENCE
            )
            connection.execute("DELETE FROM memory_facts_fts WHERE fact_id = ?", (fact_id,))
            updated = _row_to_fact(
                connection.execute(
                    f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id = ? "
                    "AND tenant_id = ? AND user_id = ?",
                    (fact_id, self.scope.tenant_id, self.scope.user_id),
                ).fetchone()
            )
            self._index(connection, updated)
        return self.get_fact(fact_id)

    def forget(self, fact_id: str) -> bool:
        """Hard-delete a fact and erase the personal source material it owns.

        Event rows are retained as provenance anchors. If another fact still
        references the same event, only the forgotten fact's text fragments are
        redacted; otherwise the event payload is fully blanked. Legacy archive
        rows are deleted because they are duplicate personal content, not an
        audit dependency.
        """
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE fact_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (fact_id, self.scope.tenant_id, self.scope.user_id),
            ).fetchone()
            if row is None:
                return False
            fact = _row_to_fact(row)
            event_ids = {
                item[0]
                for item in connection.execute(
                    "SELECT event_id FROM memory_fact_observations "
                    "WHERE fact_id = ? AND event_id IS NOT NULL",
                    (fact_id,),
                ).fetchall()
            }
            if fact.source_event_id:
                event_ids.add(fact.source_event_id)

            connection.execute(
                "DELETE FROM memory_facts WHERE fact_id = ? AND tenant_id = ? AND user_id = ?",
                (fact_id, self.scope.tenant_id, self.scope.user_id),
            )
            connection.execute(
                "DELETE FROM memory_fact_observations WHERE fact_id = ?", (fact_id,)
            )
            connection.execute(
                "DELETE FROM memory_fact_relations WHERE from_fact_id = ? OR to_fact_id = ?",
                (fact_id, fact_id),
            )
            connection.execute("DELETE FROM memory_facts_fts WHERE fact_id = ?", (fact_id,))

            # Migrated v1 rows duplicate the complete user text. They have no
            # live foreign-key consumers and must not survive definitive erase.
            archive_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories_v1_archive'"
            ).fetchone()
            if archive_exists:
                connection.execute(
                    "DELETE FROM memories_v1_archive WHERE memory_id = ? "
                    "AND tenant_id = ? AND user_id = ?",
                    (fact_id, self.scope.tenant_id, self.scope.user_id),
                )

            fragments = sorted(
                {value.strip() for value in (fact.object, fact.subject, fact.predicate) if len(value.strip()) >= 3},
                key=len,
                reverse=True,
            )
            for event_id in event_ids:
                remaining = connection.execute(
                    "SELECT 1 FROM memory_facts WHERE source_event_id = ? LIMIT 1", (event_id,)
                ).fetchone() or connection.execute(
                    "SELECT 1 FROM memory_fact_observations WHERE event_id = ? LIMIT 1", (event_id,)
                ).fetchone()
                if remaining:
                    event = connection.execute(
                        "SELECT content FROM memory_events WHERE event_id = ? "
                        "AND tenant_id = ? AND user_id = ?",
                        (event_id, self.scope.tenant_id, self.scope.user_id),
                    ).fetchone()
                    content = event[0] if event else ""
                    for fragment in fragments:
                        content = content.replace(fragment, "[effacé]")
                    connection.execute(
                        "UPDATE memory_events SET content = ? WHERE event_id = ? "
                        "AND tenant_id = ? AND user_id = ?",
                        (content, event_id, self.scope.tenant_id, self.scope.user_id),
                    )
                else:
                    connection.execute(
                        "UPDATE memory_events SET content = '[contenu effacé]', metadata = '{}' "
                        "WHERE event_id = ? AND tenant_id = ? AND user_id = ?",
                        (event_id, self.scope.tenant_id, self.scope.user_id),
                    )
        return True

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
                    "JOIN memory_facts mf ON mf.fact_id = f.fact_id "
                    "WHERE memory_facts_fts MATCH ? AND mf.tenant_id = ? AND mf.user_id = ? "
                    "ORDER BY rank LIMIT ?",
                    (match, self.scope.tenant_id, self.scope.user_id, limit),
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
                f"WHERE tenant_id = ? AND user_id = ? AND fact_id IN ({placeholders})",
                (self.scope.tenant_id, self.scope.user_id, *ranks),
            ).fetchall()
        return [(_row_to_fact(row), ranks[row["fact_id"]]) for row in facts]

    # ── observations and relations ────────────────────────────────────────

    def list_observations(self, fact_id: str) -> list[FactObservation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT observation_id, fact_id, event_id, observation_type, "
                "confidence_delta, created_at FROM memory_fact_observations "
                "WHERE fact_id = ? AND EXISTS (SELECT 1 FROM memory_facts f "
                "WHERE f.fact_id = memory_fact_observations.fact_id "
                "AND f.tenant_id = ? AND f.user_id = ?) ORDER BY created_at",
                (fact_id, self.scope.tenant_id, self.scope.user_id),
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
        if self.get_fact(from_fact_id) is None or self.get_fact(to_fact_id) is None:
            raise ValueError("facts must belong to the current scope")
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
                f"SELECT {_FACT_COLUMNS} FROM memory_facts WHERE tenant_id = ? AND user_id = ? "
                "AND fact_id IN ("
                "  SELECT to_fact_id FROM memory_fact_relations "
                "  WHERE from_fact_id = ? AND relation_type = ?"
                ")",
                (self.scope.tenant_id, self.scope.user_id,
                 fact_id, RelationType.SUPERSEDES.value),
            ).fetchall()
        return [_row_to_fact(row) for row in rows]

    # ── internals ─────────────────────────────────────────────────────────

    def _owns_event(self, event_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM memory_events WHERE event_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (event_id, self.scope.tenant_id, self.scope.user_id),
            ).fetchone() is not None

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
        entity_id=row["entity_id"],
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
