"""Entity, relation and timeline persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore
from emefa.domain.entities.schemas import (
    Entity,
    EntityKind,
    EntityScope,
    EntityStatus,
    Milestone,
    Relation,
    RelationKind,
    TimelineEntry,
    normalise_kind,
    normalise_milestone,
    normalise_relation,
    normalise_scope,
    normalise_status,
    slugify,
)

_ENTITY_COLUMNS = (
    "entity_id, kind, name, slug, scope, status, summary, attributes, "
    "created_at, updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_entity_id() -> str:
    return f"ent_{uuid.uuid4().hex[:12]}"


class EntityRepository(ScopedStore):
    ownership = Ownership.USER

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        super().__init__(database_path, scope)

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    # ── entities ──────────────────────────────────────────────────────────

    def upsert(
        self,
        kind: EntityKind | str,
        name: str,
        *,
        scope: EntityScope | str = EntityScope.BUSINESS,
        status: EntityStatus | str | None = None,
        summary: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Entity:
        """Create the entity, or update the one that is already there.

        Upsert rather than create, because the caller is usually a
        conversation: the user says "le projet Graphiste GPT" three times in a
        week and means the same project every time. Creating a second node
        would quietly split its memory in half.

        Fields left as None are not touched, so mentioning a project in
        passing never wipes the summary someone wrote for it.
        """
        cleaned_name = " ".join(name.split()).strip()[:200]
        if len(cleaned_name) < 2:
            raise ValueError("entity name must not be empty")
        kind = normalise_kind(kind)
        slug = slugify(cleaned_name)

        existing = self.find(kind, cleaned_name)
        now = _now()
        if existing is not None:
            merged = {**existing.attributes, **(attributes or {})}
            with self._connect() as connection:
                connection.execute(
                    "UPDATE entities SET name = ?, scope = ?, status = ?, summary = ?, "
                    "attributes = ?, updated_at = ? WHERE entity_id = ? "
                    "AND tenant_id = ? AND user_id = ?",
                    (
                        cleaned_name,
                        normalise_scope(scope).value if scope is not None else existing.scope.value,
                        normalise_status(status).value if status is not None else existing.status.value,
                        (summary if summary is not None else existing.summary)[:1_000],
                        json.dumps(merged, ensure_ascii=False),
                        now,
                        existing.entity_id,
                        self.scope.tenant_id,
                        self.scope.user_id,
                    ),
                )
            found = self.get(existing.entity_id)
            assert found is not None
            return found

        entity = Entity(
            entity_id=new_entity_id(),
            kind=kind,
            name=cleaned_name,
            slug=slug,
            scope=normalise_scope(scope),
            status=normalise_status(status),
            summary=(summary or "")[:1_000],
            attributes=attributes or {},
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO entities (tenant_id, user_id, {_ENTITY_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.scope.tenant_id,
                    self.scope.user_id,
                    entity.entity_id,
                    entity.kind.value,
                    entity.name,
                    entity.slug,
                    entity.scope.value,
                    entity.status.value,
                    entity.summary,
                    json.dumps(entity.attributes, ensure_ascii=False),
                    entity.created_at,
                    entity.updated_at,
                ),
            )
        return entity

    def get(self, entity_id: str) -> Entity | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_ENTITY_COLUMNS} FROM entities WHERE entity_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (entity_id, self.scope.tenant_id, self.scope.user_id),
            ).fetchone()
        return _entity_from(row) if row is not None else None

    def find(self, kind: EntityKind | str | None, name: str) -> Entity | None:
        slug = slugify(name)
        query = f"SELECT {_ENTITY_COLUMNS} FROM entities WHERE tenant_id = ? AND user_id = ? AND slug = ?"
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id, slug]
        if kind is not None:
            query += " AND kind = ?"
            parameters.append(normalise_kind(kind).value)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return _entity_from(row) if row is not None else None

    def resolve(self, name: str, kind: EntityKind | str | None = None) -> Entity | None:
        """Find an entity by what the user called it.

        Exact slug first, then a prefix match — "Graphiste" should reach
        "Graphiste GPT". Ambiguity resolves to nothing rather than to a guess:
        answering about the wrong project is worse than asking which one.
        """
        exact = self.find(kind, name)
        if exact is not None:
            return exact
        slug = slugify(name)
        if len(slug) < 3:
            return None
        query = f"SELECT {_ENTITY_COLUMNS} FROM entities WHERE tenant_id = ? AND user_id = ? AND slug LIKE ?"
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id, f"%{slug}%"]
        if kind is not None:
            query += " AND kind = ?"
            parameters.append(normalise_kind(kind).value)
        with self._connect() as connection:
            rows = connection.execute(query + " LIMIT 2", parameters).fetchall()
        return _entity_from(rows[0]) if len(rows) == 1 else None

    def list_entities(
        self,
        kind: EntityKind | str | None = None,
        scope: EntityScope | str | None = None,
        status: EntityStatus | str | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        query = f"SELECT {_ENTITY_COLUMNS} FROM entities"
        clauses: list[str] = ["tenant_id = ?", "user_id = ?"]
        parameters: list[Any] = [self.scope.tenant_id, self.scope.user_id]
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(normalise_kind(kind).value)
        if scope is not None:
            clauses.append("scope = ?")
            parameters.append(normalise_scope(scope).value)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(normalise_status(status).value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_entity_from(row) for row in rows]

    def set_status(self, entity_id: str, status: EntityStatus | str) -> Entity | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE entities SET status = ?, updated_at = ? WHERE entity_id = ? "
                "AND tenant_id = ? AND user_id = ?",
                (normalise_status(status).value, _now(), entity_id,
                 self.scope.tenant_id, self.scope.user_id),
            )
        return self.get(entity_id)

    # ── relations ─────────────────────────────────────────────────────────

    def link(
        self,
        from_entity_id: str,
        to_entity_id: str,
        kind: RelationKind | str,
        attributes: dict[str, Any] | None = None,
    ) -> Relation | None:
        """Relate two entities. Re-linking the same edge is a no-op, not a
        duplicate — the user restating a known relationship is common."""
        if from_entity_id == to_entity_id:
            return None
        if self.get(from_entity_id) is None or self.get(to_entity_id) is None:
            return None
        relation = Relation(
            relation_id=f"erl_{uuid.uuid4().hex[:12]}",
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            kind=normalise_relation(kind),
            attributes=attributes or {},
            created_at=_now(),
        )
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO entity_relations "
                    "(relation_id, from_entity_id, to_entity_id, kind, attributes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        relation.relation_id,
                        relation.from_entity_id,
                        relation.to_entity_id,
                        relation.kind.value,
                        json.dumps(relation.attributes, ensure_ascii=False),
                        relation.created_at,
                    ),
                )
            except sqlite3.IntegrityError:
                return None
        return relation

    def relations_of(self, entity_id: str) -> list[tuple[Relation, Entity, str]]:
        """Every edge touching this entity, with the entity at the other end
        and which way the edge points ("out" or "in")."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT relation_id, from_entity_id, to_entity_id, kind, attributes, "
                "created_at FROM entity_relations "
                "WHERE (from_entity_id = ? OR to_entity_id = ?) "
                "AND EXISTS (SELECT 1 FROM entities e WHERE e.entity_id = entity_relations.from_entity_id "
                "AND e.tenant_id = ? AND e.user_id = ?) "
                "AND EXISTS (SELECT 1 FROM entities e WHERE e.entity_id = entity_relations.to_entity_id "
                "AND e.tenant_id = ? AND e.user_id = ?)",
                (entity_id, entity_id, self.scope.tenant_id, self.scope.user_id,
                 self.scope.tenant_id, self.scope.user_id),
            ).fetchall()
        edges: list[tuple[Relation, Entity, str]] = []
        for row in rows:
            relation = Relation(
                relation_id=row["relation_id"],
                from_entity_id=row["from_entity_id"],
                to_entity_id=row["to_entity_id"],
                kind=normalise_relation(row["kind"]),
                attributes=json.loads(row["attributes"] or "{}"),
                created_at=row["created_at"],
            )
            outgoing = relation.from_entity_id == entity_id
            other_id = relation.to_entity_id if outgoing else relation.from_entity_id
            other = self.get(other_id)
            if other is not None:
                edges.append((relation, other, "out" if outgoing else "in"))
        return edges

    # ── timeline ──────────────────────────────────────────────────────────

    def record_milestone(
        self,
        entity_id: str,
        milestone: Milestone | str,
        headline: str,
        occurred_at: str | None = None,
        event_id: str | None = None,
    ) -> TimelineEntry:
        if self.get(entity_id) is None:
            raise ValueError("entity not found in scope")
        entry = TimelineEntry(
            entry_id=f"tml_{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            milestone=normalise_milestone(milestone),
            headline=" ".join(headline.split()).strip()[:300],
            occurred_at=occurred_at or _now(),
            event_id=event_id,
            created_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO entity_timeline "
                "(entry_id, tenant_id, user_id, entity_id, milestone, headline, occurred_at, event_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.entry_id,
                    self.scope.tenant_id,
                    self.scope.user_id,
                    entry.entity_id,
                    entry.milestone.value,
                    entry.headline,
                    entry.occurred_at,
                    entry.event_id,
                    entry.created_at,
                ),
            )
        return entry

    def timeline(self, entity_id: str, limit: int = 100) -> list[TimelineEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT entry_id, entity_id, milestone, headline, occurred_at, "
                "event_id, created_at FROM entity_timeline WHERE entity_id = ? "
                "AND tenant_id = ? AND user_id = ? "
                "ORDER BY occurred_at, entry_id LIMIT ?",
                (entity_id, self.scope.tenant_id, self.scope.user_id, limit),
            ).fetchall()
        return [
            TimelineEntry(
                entry_id=row["entry_id"],
                entity_id=row["entity_id"],
                milestone=normalise_milestone(row["milestone"]),
                headline=row["headline"],
                occurred_at=row["occurred_at"],
                event_id=row["event_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT kind, COUNT(*) AS total FROM entities "
                "WHERE tenant_id = ? AND user_id = ? GROUP BY kind",
                (self.scope.tenant_id, self.scope.user_id),
            ).fetchall()
        return {row["kind"]: int(row["total"]) for row in rows}


def _entity_from(row: sqlite3.Row) -> Entity:
    return Entity(
        entity_id=row["entity_id"],
        kind=normalise_kind(row["kind"]),
        name=row["name"],
        slug=row["slug"],
        scope=normalise_scope(row["scope"]),
        status=normalise_status(row["status"]),
        summary=row["summary"],
        attributes=json.loads(row["attributes"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
