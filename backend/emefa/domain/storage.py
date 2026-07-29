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
    # 3 — durable conversation history for the EMEFA runtime.
    (
        f"""
        CREATE TABLE conversation_turns (
            turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            conversation_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX idx_conversation_turns_lookup
        ON conversation_turns(conversation_id, turn_id)
        """,
    ),
    # 4 — pending consequential actions awaiting user approval.
    (
        f"""
        CREATE TABLE pending_actions (
            action_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            conversation_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            call_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        )
        """,
        """
        CREATE INDEX idx_pending_actions_conversation
        ON pending_actions(conversation_id, status)
        """,
    ),
    # 5 — tasks and commitments (administrative assistant foundation).
    (
        f"""
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """,
        "CREATE INDEX idx_tasks_open ON tasks(user_id, status, due_date)",
    ),
    # 6 — durable, user-controllable memory (Phase 4 MVP).
    (
        f"""
        CREATE TABLE memories (
            memory_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            category TEXT NOT NULL DEFAULT 'fact',
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'conversation',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_memories_user ON memories(user_id, created_at)",
    ),
    # 7 — public website context used for automatic profile preconfiguration.
    (
        "ALTER TABLE business_profiles ADD COLUMN website_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE business_profiles ADD COLUMN website_summary TEXT NOT NULL DEFAULT ''",
    ),
    # 8 — local sales pipeline (business development seed).
    (
        f"""
        CREATE TABLE prospects (
            prospect_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            name TEXT NOT NULL,
            company TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'nouveau',
            notes TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            next_action_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_prospects_stage ON prospects(user_id, stage, next_action_date)",
    ),
    # 9 — proactive daily briefings (recurring workflow seed).
    (
        f"""
        CREATE TABLE briefings (
            brief_date TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            content TEXT NOT NULL,
            emailed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    # 10 — governed command center: initiatives, routines and auditable runs.
    (
        f"""
        CREATE TABLE initiatives (
            initiative_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            objective TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'proposed',
            priority TEXT NOT NULL DEFAULT 'normal',
            risk TEXT NOT NULL DEFAULT 'low',
            autonomy_level INTEGER NOT NULL DEFAULT 0,
            next_action TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_initiatives_status ON initiatives(user_id, status, priority, due_date)",
        f"""
        CREATE TABLE routines (
            routine_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            schedule_kind TEXT NOT NULL DEFAULT 'manual',
            schedule_hour INTEGER,
            schedule_weekday INTEGER,
            enabled INTEGER NOT NULL DEFAULT 1,
            requires_confirmation INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_routines_enabled ON routines(user_id, enabled, schedule_kind)",
        f"""
        CREATE TABLE routine_runs (
            run_id TEXT PRIMARY KEY,
            routine_id TEXT NOT NULL REFERENCES routines(routine_id) ON DELETE CASCADE,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            status TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT '',
            action_id TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        )
        """,
        "CREATE INDEX idx_routine_runs_recent ON routine_runs(routine_id, started_at)",
    ),
    # 11 — executive profile depth + conversational onboarding state (V1 MVP).
    (
        *(
            f"ALTER TABLE business_profiles ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
            for column in (
                # Personal profile
                "preferred_name",
                "country",
                "city",
                "timezone",
                "working_hours",
                # Company
                "products",
                "services",
                "organization",
                "collaborators",
                # Activity
                "clients",
                "suppliers",
                "partners",
                # Objectives
                "annual_goals",
                "quarterly_goals",
                "current_priorities",
                "challenges",
                # Preferences
                "autonomy_level",
                "communication_style",
                "report_frequency",
                "organization_preferences",
            )
        ),
        f"""
        CREATE TABLE onboarding_state (
            user_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            started_at TEXT,
            completed_at TEXT,
            skipped_topics TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"INSERT INTO onboarding_state (user_id) VALUES ('{DEFAULT_USER_ID}')",
    ),
    # 12 — executive CRM: contacts, projects, deals, contracts, interactions.
    (
        f"""
        CREATE TABLE contacts (
            contact_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'client',
            company TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'actif',
            follow_up_days INTEGER NOT NULL DEFAULT 0,
            last_interaction_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_contacts_kind ON contacts(user_id, kind, status)",
        f"""
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            name TEXT NOT NULL,
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE SET NULL,
            objective TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'cadrage',
            health TEXT NOT NULL DEFAULT 'ok',
            next_step TEXT NOT NULL DEFAULT '',
            blocker TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_projects_status ON projects(user_id, status, health)",
        f"""
        CREATE TABLE deals (
            deal_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE SET NULL,
            project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
            amount REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'XOF',
            stage TEXT NOT NULL DEFAULT 'brouillon',
            sent_at TEXT,
            response_due_date TEXT,
            document_id TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_deals_stage ON deals(user_id, stage, response_due_date)",
        f"""
        CREATE TABLE contracts (
            contract_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE SET NULL,
            project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
            start_date TEXT,
            end_date TEXT,
            value REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'XOF',
            status TEXT NOT NULL DEFAULT 'actif',
            notice_days INTEGER NOT NULL DEFAULT 30,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_contracts_end ON contracts(user_id, status, end_date)",
        f"""
        CREATE TABLE interactions (
            interaction_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE CASCADE,
            project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'note',
            summary TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_interactions_contact ON interactions(contact_id, occurred_at)",
        "CREATE INDEX idx_interactions_project ON interactions(project_id, occurred_at)",
    ),
    # 13 — meeting engine: minutes, decisions, actions.
    (
        f"""
        CREATE TABLE meetings (
            meeting_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            participants TEXT NOT NULL DEFAULT '',
            project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE SET NULL,
            summary TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            document_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_meetings_recent ON meetings(user_id, occurred_at)",
        """
        CREATE TABLE meeting_decisions (
            decision_id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(meeting_id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE meeting_actions (
            meeting_action_id TEXT PRIMARY KEY,
            meeting_id TEXT NOT NULL REFERENCES meetings(meeting_id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            task_id TEXT,
            position INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE INDEX idx_meeting_actions_meeting ON meeting_actions(meeting_id, position)",
    ),
    # 14 — office artifact index (Word/Excel/PowerPoint share one catalogue).
    (
        f"""
        CREATE TABLE artifacts (
            artifact_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            kind TEXT NOT NULL DEFAULT 'document',
            title TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_artifacts_recent ON artifacts(user_id, updated_at)",
    ),
    # 15 — evening report + per-user report section preferences.
    (
        f"""
        CREATE TABLE evening_reports (
            brief_date TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            content TEXT NOT NULL,
            emailed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE report_preferences (
            user_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            morning_sections TEXT NOT NULL DEFAULT '',
            evening_sections TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"INSERT INTO report_preferences (user_id) VALUES ('{DEFAULT_USER_ID}')",
    ),
    # 16 — local agenda. Times are stored as naive local ISO strings
    # ("YYYY-MM-DDTHH:MM"), consistent with the date handling elsewhere; the
    # executive's timezone lives on their profile.
    (
        f"""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            title TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'rendez_vous',
            starts_at TEXT NOT NULL,
            ends_at TEXT,
            location TEXT NOT NULL DEFAULT '',
            participants TEXT NOT NULL DEFAULT '',
            contact_id TEXT REFERENCES contacts(contact_id) ON DELETE SET NULL,
            project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
            notes TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            external_id TEXT,
            meeting_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_events_when ON events(user_id, starts_at)",
        # An external calendar must never create the same event twice.
        "CREATE UNIQUE INDEX idx_events_external ON events(source, external_id)",
    ),
    # 17 — per-user connected accounts (Gmail, calendars, …).
    #
    # The secret is stored encrypted, never in clear, and every row carries the
    # tenant and user that own it. One connected account per provider per user,
    # so "Jean's Gmail" and "Amina's Gmail" are structurally distinct rows that
    # no query can conflate.
    (
        f"""
        CREATE TABLE connected_accounts (
            account_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            provider TEXT NOT NULL,
            account_label TEXT NOT NULL,
            secret_ciphertext TEXT NOT NULL,
            secret_nonce TEXT NOT NULL,
            key_version INTEGER NOT NULL DEFAULT 1,
            scopes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            expires_at TEXT,
            last_used_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE UNIQUE INDEX idx_connected_accounts_owner "
        "ON connected_accounts(tenant_id, user_id, provider)",
        "CREATE INDEX idx_connected_accounts_status "
        "ON connected_accounts(tenant_id, user_id, status)",
    ),
    # 18 — a consistent ownership shape across every business resource.
    #
    # Company resources record who created and last touched them; the read
    # predicate stays tenant-wide so colleagues share one CRM. Tasks gain an
    # assignee. Meeting children gain the tenant they were missing entirely.
    (
        *(
            f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL "
            f"DEFAULT '{DEFAULT_USER_ID}'"
            for table in (
                "contacts", "projects", "deals", "contracts", "interactions",
                "meetings", "prospects", "initiatives", "routines", "tasks",
                "events", "artifacts",
            )
            for column in ("created_by_user_id", "updated_by_user_id")
        ),
        # Who is expected to do it; NULL means "the company, unassigned".
        "ALTER TABLE tasks ADD COLUMN assigned_to_user_id TEXT",
        "CREATE INDEX idx_tasks_assignee ON tasks(tenant_id, assigned_to_user_id, status)",
        # Meeting decisions and actions had no tenant at all: they were reachable
        # only through their parent, which is not a security boundary.
        f"ALTER TABLE meeting_decisions ADD COLUMN tenant_id TEXT NOT NULL "
        f"DEFAULT '{DEFAULT_TENANT_ID}'",
        f"ALTER TABLE meeting_actions ADD COLUMN tenant_id TEXT NOT NULL "
        f"DEFAULT '{DEFAULT_TENANT_ID}'",
        "CREATE INDEX idx_meeting_decisions_tenant ON meeting_decisions(tenant_id, meeting_id)",
        "CREATE INDEX idx_meeting_actions_tenant ON meeting_actions(tenant_id, meeting_id)",
        # Company-wide indexes for the reads that matter most.
        "CREATE INDEX idx_contacts_tenant ON contacts(tenant_id, kind, status)",
        "CREATE INDEX idx_projects_tenant ON projects(tenant_id, status, health)",
        "CREATE INDEX idx_deals_tenant ON deals(tenant_id, stage)",
        "CREATE INDEX idx_contracts_tenant ON contracts(tenant_id, status, end_date)",
    ),
    # 19 — real SaaS accounts: a user is now something you can sign up as,
    # verify, log into and invite, instead of a row seeded by a migration.
    #
    # The columns default to the values the existing single-tenant instance
    # already behaves as (an active owner with no password), so the deployed
    # enrollment-code path keeps working untouched while the account path is
    # built beside it.
    (
        "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'owner'",
        "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN email_verified_at TEXT",
        "ALTER TABLE users ADD COLUMN last_login_at TEXT",
        # Emails are stored already normalised. The index is partial so the
        # seeded default user, which has none, does not occupy the empty slot.
        "CREATE UNIQUE INDEX idx_users_email ON users(email) WHERE email <> ''",
        "CREATE INDEX idx_users_tenant ON users(tenant_id, status)",
        # Single-use, expiring secrets for email verification and password
        # reset. Only the hash is stored: a database read cannot be replayed
        # as a valid link.
        """
        CREATE TABLE auth_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(user_id),
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX idx_auth_tokens_user ON auth_tokens(user_id, purpose, consumed_at)",
        """
        CREATE TABLE invitations (
            invitation_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            token_hash TEXT NOT NULL UNIQUE,
            invited_by_user_id TEXT NOT NULL REFERENCES users(user_id),
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            accepted_user_id TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        # One live invitation per address per company; re-inviting replaces it.
        "CREATE UNIQUE INDEX idx_invitations_live ON invitations(tenant_id, email) "
        "WHERE accepted_at IS NULL AND revoked_at IS NULL",
        # A device belongs to the account that signed in on it.
        "CREATE INDEX idx_devices_user ON devices(user_id)",
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
