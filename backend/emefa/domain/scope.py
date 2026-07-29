"""Tenant scoping, enforced in one place instead of twenty.

ADR-001 reserved the `tenant → user → assistant` shape and every table carries
the columns, but until now only connected accounts were actually *resolved*
through them: two tenants would have shared one CRM.

Scoping twenty hand-written queries is how isolation bugs happen — one
forgotten `AND tenant_id = ?` is a silent cross-tenant read. So the scope is
applied by the store, not by the query author:

* :meth:`ScopedStore.fetch_one` / :meth:`fetch_all` take a ``WHERE`` fragment
  and prepend the scope predicate themselves;
* :meth:`insert` stamps ``tenant_id`` and ``user_id`` onto every row;
* :meth:`update_scoped` / :meth:`delete_scoped` add the scope to the key.

A caller cannot express an unscoped query through this interface, which is the
point. Anything that genuinely needs to cross tenants must reach for raw
storage deliberately and visibly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.storage import DEFAULT_TENANT_ID, DEFAULT_USER_ID


@dataclass(frozen=True, slots=True)
class Scope:
    """Who owns the rows a repository may see."""

    tenant_id: str = DEFAULT_TENANT_ID
    user_id: str = DEFAULT_USER_ID

    @property
    def predicate(self) -> str:
        return "tenant_id = ? AND user_id = ?"

    @property
    def values(self) -> tuple[str, str]:
        return (self.tenant_id, self.user_id)

    def is_default(self) -> bool:
        return self.tenant_id == DEFAULT_TENANT_ID and self.user_id == DEFAULT_USER_ID


#: The single-tenant instance every existing deployment runs as.
DEFAULT_SCOPE = Scope()


class ScopedStore:
    """Base for repositories whose rows belong to one tenant and one user."""

    def __init__(self, database_path: Path, scope: Scope | None = None) -> None:
        self.database_path = Path(database_path)
        self.scope = scope or DEFAULT_SCOPE
        storage.run_migrations(self.database_path)

    def for_scope(self, scope: Scope) -> "ScopedStore":
        """A sibling bound to another owner. Cheap: repositories hold a path."""
        return type(self)(self.database_path, scope)

    # -- reads ------------------------------------------------------------

    def _scoped_sql(self, columns: str, table: str, where: str, tail: str) -> str:
        clause = f"WHERE {self.scope.predicate}"
        if where:
            clause += f" AND ({where})"
        return f"SELECT {columns} FROM {table} {clause} {tail}".strip()

    def fetch_one(
        self,
        columns: str,
        table: str,
        where: str = "",
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                self._scoped_sql(columns, table, where, ""),
                (*self.scope.values, *parameters),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_all(
        self,
        columns: str,
        table: str,
        where: str = "",
        parameters: tuple[Any, ...] = (),
        tail: str = "",
    ) -> list[dict[str, Any]]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                self._scoped_sql(columns, table, where, tail),
                (*self.scope.values, *parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- writes -----------------------------------------------------------

    def insert(self, table: str, values: dict[str, Any]) -> None:
        """Insert, stamping the owner. A row cannot be created unowned."""
        owned = {**values, "tenant_id": self.scope.tenant_id, "user_id": self.scope.user_id}
        columns = ", ".join(owned)
        placeholders = ", ".join("?" for _ in owned)
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(owned.values()),
            )

    def update_scoped(
        self,
        table: str,
        key: str,
        key_value: str,
        values: dict[str, Any],
        touch_updated_at: bool = True,
    ) -> int:
        if not values:
            return 0
        assignments = ", ".join(f"{column} = ?" for column in values)
        if touch_updated_at:
            assignments += ", updated_at = CURRENT_TIMESTAMP"
        with storage.connect(self.database_path) as connection:
            return connection.execute(
                f"UPDATE {table} SET {assignments} "
                f"WHERE {key} = ? AND {self.scope.predicate}",
                (*values.values(), key_value, *self.scope.values),
            ).rowcount

    def delete_scoped(self, table: str, key: str, key_value: str) -> bool:
        with storage.connect(self.database_path) as connection:
            return connection.execute(
                f"DELETE FROM {table} WHERE {key} = ? AND {self.scope.predicate}",
                (key_value, *self.scope.values),
            ).rowcount > 0
