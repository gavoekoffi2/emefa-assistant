"""Shared SQLite access and numbered schema migrations (ADR-001)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Fixed identifiers for the single-tenant instance mode defined in ADR-001.
# Resolved server-side only; never accepted from a client.
DEFAULT_TENANT_ID = "ten_default"
DEFAULT_USER_ID = "usr_default"
DEFAULT_ASSISTANT_ID = "ast_default"

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    # 1 — original device store (kept identical for existing databases).
    (
        """
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    # 2 — identity hierarchy and profiles (ADR-001 single-tenant seeds).
    (
        """
        CREATE TABLE tenants (
            tenant_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE assistants (
            assistant_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            user_id TEXT NOT NULL REFERENCES users(user_id),
            name TEXT NOT NULL DEFAULT 'EMEFA',
            primary_language TEXT NOT NULL DEFAULT 'fr',
            interaction_style TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE business_profiles (
            assistant_id TEXT PRIMARY KEY REFERENCES assistants(assistant_id),
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            owner_name TEXT NOT NULL DEFAULT '',
            owner_role TEXT NOT NULL DEFAULT '',
            company_name TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            offer TEXT NOT NULL DEFAULT '',
            target_customers TEXT NOT NULL DEFAULT '',
            goals TEXT NOT NULL DEFAULT '',
            constraints_notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"INSERT INTO tenants (tenant_id, name) VALUES ('{DEFAULT_TENANT_ID}', 'Instance privée')",
        f"""
        INSERT INTO users (user_id, tenant_id, display_name)
        VALUES ('{DEFAULT_USER_ID}', '{DEFAULT_TENANT_ID}', 'Propriétaire')
        """,
        f"""
        INSERT INTO assistants (assistant_id, tenant_id, user_id)
        VALUES ('{DEFAULT_ASSISTANT_ID}', '{DEFAULT_TENANT_ID}', '{DEFAULT_USER_ID}')
        """,
        f"""
        INSERT INTO business_profiles (assistant_id, tenant_id)
        VALUES ('{DEFAULT_ASSISTANT_ID}', '{DEFAULT_TENANT_ID}')
        """,
        f"ALTER TABLE devices ADD COLUMN user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}'",
    ),
)


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def run_migrations(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        current = int(row[0]) if row is not None and row[0] is not None else 0
        for version, statements in enumerate(MIGRATIONS[current:], start=current + 1):
            for statement in statements:
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))


def schema_version(database_path: Path) -> int:
    with connect(database_path) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0
