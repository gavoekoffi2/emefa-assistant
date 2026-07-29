"""Regression tests for the two incompatible historical v20 schemas."""

from __future__ import annotations

import sqlite3

import pytest

from emefa.domain import storage


def _migration_versions(database) -> list[int]:
    with storage.connect(database) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]


def _objects(database, object_type: str) -> set[str]:
    with storage.connect(database) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", (object_type,)
            )
        }


def _columns(database, table: str) -> set[str]:
    with storage.connect(database) as connection:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _production_main_migrations() -> tuple[tuple[str, ...], ...]:
    """Recreate the schema that production called v20 before the rebase."""
    # The historical main-v20 migration renamed the flat table.  The unified
    # v21 instead copies it so Premium explicit memories can coexist.
    memory_kernel = storage.MIGRATIONS[20][:-2] + (
        "ALTER TABLE memories RENAME TO memories_v1_archive",
    )
    accounts = (
        f"""
        CREATE TABLE accounts (
            account_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{storage.DEFAULT_TENANT_ID}'
                REFERENCES tenants(tenant_id),
            user_id TEXT NOT NULL DEFAULT '{storage.DEFAULT_USER_ID}'
                REFERENCES users(user_id),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'owner',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT
        )
        """,
        "CREATE INDEX idx_accounts_tenant ON accounts(tenant_id, status)",
        "ALTER TABLE devices ADD COLUMN account_id TEXT REFERENCES accounts(account_id)",
    )
    webauthn = tuple(
        statement.replace(
            "REFERENCES users(user_id)", "REFERENCES accounts(account_id)"
        )
        for statement in storage.MIGRATIONS[28]
    )
    return storage.MIGRATIONS[:10] + (
        memory_kernel,
        accounts,
        storage.MIGRATIONS[22],
        storage.MIGRATIONS[23],
        storage.MIGRATIONS[24],
        storage.MIGRATIONS[25],
        storage.MIGRATIONS[26],
        storage.MIGRATIONS[27],
        webauthn,
        (
            "CREATE UNIQUE INDEX idx_accounts_single_owner "
            "ON accounts(role) WHERE role = 'owner'",
        ),
    )


def test_fresh_v0_applies_all_migrations_and_is_idempotent(tmp_path):
    database = tmp_path / "fresh.db"

    storage.run_migrations(database)
    with storage.connect(database) as connection:
        connection.execute(
            "INSERT INTO contacts (contact_id, name) VALUES ('contact-fresh', 'Afi')"
        )
    storage.run_migrations(database)

    assert _migration_versions(database) == list(range(1, len(storage.MIGRATIONS) + 1))
    assert {"contacts", "memory_events"} <= _objects(database, "table")
    assert "idx_users_tenant_owner" in _objects(database, "index")
    with storage.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM contacts WHERE contact_id = 'contact-fresh'"
        ).fetchone()[0] == "Afi"
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO users (user_id, tenant_id, display_name, role) "
                "VALUES ('second-owner', ?, 'Deuxième', 'owner')",
                (storage.DEFAULT_TENANT_ID,),
            )
        connection.execute(
            "INSERT INTO tenants (tenant_id, name) VALUES ('tenant-two', 'Deux')"
        )
        connection.execute(
            "INSERT INTO users (user_id, tenant_id, display_name, role) "
            "VALUES ('other-owner', 'tenant-two', 'Autre', 'owner')"
        )


def test_premium_v20_applies_main_v21_to_v30(tmp_path, monkeypatch):
    database = tmp_path / "premium-v20.db"
    complete_migrations = storage.MIGRATIONS
    monkeypatch.setattr(storage, "MIGRATIONS", complete_migrations[:20])
    storage.run_migrations(database)
    with storage.connect(database) as connection:
        connection.execute(
            "INSERT INTO contacts (contact_id, name) VALUES ('premium-contact', 'Kossi')"
        )
    monkeypatch.setattr(storage, "MIGRATIONS", complete_migrations)

    storage.run_migrations(database)
    storage.run_migrations(database)

    assert _migration_versions(database) == list(range(1, len(storage.MIGRATIONS) + 1))
    assert "memory_events" in _objects(database, "table")
    with storage.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM contacts WHERE contact_id = 'premium-contact'"
        ).fetchone()[0] == "Kossi"


def test_production_main_v20_backfills_premium_without_replaying_main(
    tmp_path, monkeypatch
):
    database = tmp_path / "production-main-v20.db"
    complete_migrations = storage.MIGRATIONS
    monkeypatch.setattr(storage, "MIGRATIONS", _production_main_migrations())
    storage.run_migrations(database)
    with storage.connect(database) as connection:
        connection.execute(
            "INSERT INTO memories_v1_archive (memory_id, content) "
            "VALUES ('legacy-memory', 'Donnée historique')"
        )
        connection.execute(
            "INSERT INTO memory_events "
            "(event_id, type, source, content) "
            "VALUES ('main-event', 'message', 'production', 'À préserver')"
        )
        connection.execute(
            "INSERT INTO accounts "
            "(account_id, email, password_hash, display_name) "
            "VALUES ('legacy-account', 'owner@example.test', 'hash', 'Legacy Owner')"
        )
        connection.execute(
            "INSERT INTO webauthn_credentials "
            "(credential_id, account_id, public_key, label, sign_count) "
            "VALUES ('legacy-credential', 'legacy-account', 'public-key', 'Téléphone', 7)"
        )
    monkeypatch.setattr(storage, "MIGRATIONS", complete_migrations)

    storage.run_migrations(database)
    storage.run_migrations(database)

    assert _migration_versions(database) == list(range(1, len(storage.MIGRATIONS) + 1))
    assert "contacts" in _objects(database, "table")
    assert {"preferred_name", "autonomy_level"} <= _columns(
        database, "business_profiles"
    )
    assert {"email", "password_hash", "role", "status"} <= _columns(
        database, "users"
    )
    assert "idx_users_tenant_owner" in _objects(database, "index")
    with storage.connect(database) as connection:
        assert connection.execute(
            "SELECT content FROM memories_v1_archive WHERE memory_id = 'legacy-memory'"
        ).fetchone()[0] == "Donnée historique"
        assert connection.execute(
            "SELECT content FROM memory_events WHERE event_id = 'main-event'"
        ).fetchone()[0] == "À préserver"
        migrated_user = connection.execute(
            "SELECT email, password_hash, display_name, role, status FROM users "
            "WHERE user_id = ?",
            (storage.DEFAULT_USER_ID,),
        ).fetchone()
        assert tuple(migrated_user) == (
            "owner@example.test",
            "hash",
            "Legacy Owner",
            "owner",
            "active",
        )
        credential = connection.execute(
            "SELECT account_id, public_key, label, sign_count "
            "FROM webauthn_credentials WHERE credential_id = 'legacy-credential'"
        ).fetchone()
        assert tuple(credential) == (
            storage.DEFAULT_USER_ID,
            "public-key",
            "Téléphone",
            7,
        )
        foreign_keys = connection.execute(
            'PRAGMA foreign_key_list("webauthn_credentials")'
        ).fetchall()
        assert any(row[2] == "users" and row[4] == "user_id" for row in foreign_keys)


def test_migration_failure_rolls_back_schema_data_and_versions(tmp_path, monkeypatch):
    database = tmp_path / "rollback.db"
    monkeypatch.setattr(
        storage,
        "MIGRATIONS",
        (
            (
                "CREATE TABLE migration_probe (value TEXT)",
                "INSERT INTO migration_probe VALUES ('must rollback')",
            ),
            ("CREATE TABLE broken (",),
        ),
    )

    with pytest.raises(sqlite3.OperationalError):
        storage.run_migrations(database)

    assert "migration_probe" not in _objects(database, "table")
    assert "schema_migrations" not in _objects(database, "table")
