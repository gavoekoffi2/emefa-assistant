"""Tenant scoping, enforced in one place instead of everywhere.

Two questions have to be answered for every table, and getting the second one
wrong is as damaging as forgetting the first:

**Who may see this row?** — the tenant. One forgotten `AND tenant_id = ?` is a
silent cross-company read, so the predicate is applied by the store, never by
the query author:

* :meth:`ScopedStore.fetch_one` / :meth:`fetch_all` prepend it;
* :meth:`insert` stamps the owner and the author onto every row;
* :meth:`update_scoped` / :meth:`delete_scoped` add it to the key.

A caller cannot express an unscoped query through this interface. Anything that
genuinely must cross tenants has to reach for :mod:`emefa.domain.storage`
deliberately and visibly, and say why.

**Does it belong to the company or to one person?** — :class:`Ownership`.

``TENANT``  A client, a project, a quotation, a document. It belongs to the
            *company*: two colleagues must see the same one. Filtering these
            by user as well would quietly give each employee a private CRM.

``USER``    A calendar, a conversation, a connected mailbox, a personal
            preference. It belongs to one member, inside their tenant.

Both modes always filter by tenant; ``USER`` adds the person.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from emefa.domain import storage
from emefa.domain.storage import DEFAULT_TENANT_ID, DEFAULT_USER_ID


class Ownership(str, Enum):
    """Whether a table's rows belong to the company or to one of its members."""

    TENANT = "tenant"
    USER = "user"


@dataclass(frozen=True, slots=True)
class Scope:
    """Who is asking, and on behalf of which company."""

    tenant_id: str = DEFAULT_TENANT_ID
    user_id: str = DEFAULT_USER_ID

    def predicate(self, ownership: Ownership = Ownership.TENANT) -> str:
        if ownership is Ownership.USER:
            return "tenant_id = ? AND user_id = ?"
        return "tenant_id = ?"

    def values(self, ownership: Ownership = Ownership.TENANT) -> tuple[str, ...]:
        if ownership is Ownership.USER:
            return (self.tenant_id, self.user_id)
        return (self.tenant_id,)

    def is_default(self) -> bool:
        return self.tenant_id == DEFAULT_TENANT_ID and self.user_id == DEFAULT_USER_ID


#: The single-tenant instance every existing deployment runs as.
DEFAULT_SCOPE = Scope()


class ScopedStore:
    """Base for repositories whose rows belong to a tenant.

    ``ownership`` sets the default for the store; individual calls may override
    it for a table that differs from its siblings.
    """

    #: Default ownership for this repository's tables.
    ownership: Ownership = Ownership.TENANT

    def __init__(
        self,
        database_path: Path,
        scope: Scope | None = None,
        ownership: Ownership | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.scope = scope or DEFAULT_SCOPE
        if ownership is not None:
            self.ownership = ownership
        storage.run_migrations(self.database_path)

    def for_scope(self, scope: Scope) -> "ScopedStore":
        """A sibling bound to another owner. Cheap: repositories hold a path."""
        return type(self)(self.database_path, scope)

    def _mode(self, ownership: Ownership | None) -> Ownership:
        return self.ownership if ownership is None else ownership

    # -- reads ------------------------------------------------------------

    def _scoped_sql(
        self,
        columns: str,
        table: str,
        where: str,
        tail: str,
        ownership: Ownership | None = None,
    ) -> str:
        clause = f"WHERE {self.scope.predicate(self._mode(ownership))}"
        if where:
            clause += f" AND ({where})"
        return f"SELECT {columns} FROM {table} {clause} {tail}".strip()

    def fetch_one(
        self,
        columns: str,
        table: str,
        where: str = "",
        parameters: tuple[Any, ...] = (),
        ownership: Ownership | None = None,
    ) -> dict[str, Any] | None:
        with storage.connect(self.database_path) as connection:
            row = connection.execute(
                self._scoped_sql(columns, table, where, "", ownership),
                (*self.scope.values(self._mode(ownership)), *parameters),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_all(
        self,
        columns: str,
        table: str,
        where: str = "",
        parameters: tuple[Any, ...] = (),
        tail: str = "",
        ownership: Ownership | None = None,
    ) -> list[dict[str, Any]]:
        with storage.connect(self.database_path) as connection:
            rows = connection.execute(
                self._scoped_sql(columns, table, where, tail, ownership),
                (*self.scope.values(self._mode(ownership)), *parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self, table: str, where: str = "", parameters: tuple[Any, ...] = ()) -> int:
        row = self.fetch_one("COUNT(*) AS total", table, where, parameters)
        return int(row["total"]) if row else 0

    # -- writes -----------------------------------------------------------

    def insert(
        self, table: str, values: dict[str, Any], ownership: Ownership | None = None
    ) -> None:
        """Insert, stamping the owner and the author. A row cannot be unowned.

        ``user_id`` is written for both modes: on a tenant-owned row it records
        who created it, which the audit trail needs, while the *read* predicate
        deliberately ignores it.
        """
        owned = {
            **values,
            "tenant_id": self.scope.tenant_id,
            "user_id": self.scope.user_id,
        }
        columns = self._columns_of(table)
        if "created_by_user_id" in columns:
            owned.setdefault("created_by_user_id", self.scope.user_id)
        if "updated_by_user_id" in columns:
            owned.setdefault("updated_by_user_id", self.scope.user_id)
        owned = {key: value for key, value in owned.items() if key in columns}
        names = ", ".join(owned)
        placeholders = ", ".join("?" for _ in owned)
        with storage.connect(self.database_path) as connection:
            connection.execute(
                f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                tuple(owned.values()),
            )

    def update_scoped(
        self,
        table: str,
        key: str,
        key_value: str,
        values: dict[str, Any],
        touch_updated_at: bool = True,
        ownership: Ownership | None = None,
    ) -> int:
        if not values:
            return 0
        columns = self._columns_of(table)
        payload = dict(values)
        if "updated_by_user_id" in columns:
            payload["updated_by_user_id"] = self.scope.user_id
        assignments = ", ".join(f"{column} = ?" for column in payload)
        if touch_updated_at and "updated_at" in columns:
            assignments += ", updated_at = CURRENT_TIMESTAMP"
        mode = self._mode(ownership)
        with storage.connect(self.database_path) as connection:
            return connection.execute(
                f"UPDATE {table} SET {assignments} "
                f"WHERE {key} = ? AND {self.scope.predicate(mode)}",
                (*payload.values(), key_value, *self.scope.values(mode)),
            ).rowcount

    def delete_scoped(
        self, table: str, key: str, key_value: str, ownership: Ownership | None = None
    ) -> bool:
        mode = self._mode(ownership)
        with storage.connect(self.database_path) as connection:
            return connection.execute(
                f"DELETE FROM {table} WHERE {key} = ? AND {self.scope.predicate(mode)}",
                (key_value, *self.scope.values(mode)),
            ).rowcount > 0

    # -- schema -----------------------------------------------------------

    _COLUMN_CACHE: dict[tuple[str, str], frozenset[str]] = {}

    def _columns_of(self, table: str) -> frozenset[str]:
        key = (str(self.database_path), table)
        cached = ScopedStore._COLUMN_CACHE.get(key)
        if cached is None:
            with storage.connect(self.database_path) as connection:
                cached = frozenset(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
            ScopedStore._COLUMN_CACHE[key] = cached
        return cached
