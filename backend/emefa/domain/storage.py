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
    # 20 — uniqueness that includes the tenant.
    #
    # Scoping every *read* is not sufficient on its own: a UNIQUE constraint
    # that omits tenant_id is still shared across companies. These three
    # tables keyed their rows on a date or a user alone, so the first company
    # to generate a report on a given day made that day unavailable to every
    # other company on the instance — a cross-tenant failure that no amount
    # of correct WHERE clauses would have prevented.
    #
    # SQLite cannot alter a primary key, so each table is rebuilt in place.
    # The daily reports are personal, hence (tenant, user, date).
    (
        """
        CREATE TABLE briefings_v2 (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            brief_date TEXT NOT NULL,
            content TEXT NOT NULL,
            emailed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id, brief_date)
        )
        """,
        """
        INSERT INTO briefings_v2 (tenant_id, user_id, brief_date, content, emailed, created_at)
        SELECT tenant_id, user_id, brief_date, content, emailed, created_at FROM briefings
        """,
        "DROP TABLE briefings",
        "ALTER TABLE briefings_v2 RENAME TO briefings",
        """
        CREATE TABLE evening_reports_v2 (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            brief_date TEXT NOT NULL,
            content TEXT NOT NULL,
            emailed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id, brief_date)
        )
        """,
        """
        INSERT INTO evening_reports_v2
            (tenant_id, user_id, brief_date, content, emailed, created_at)
        SELECT tenant_id, user_id, brief_date, content, emailed, created_at FROM evening_reports
        """,
        "DROP TABLE evening_reports",
        "ALTER TABLE evening_reports_v2 RENAME TO evening_reports",
        """
        CREATE TABLE report_preferences_v2 (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            morning_sections TEXT NOT NULL DEFAULT '',
            evening_sections TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        )
        """,
        """
        INSERT INTO report_preferences_v2
            (tenant_id, user_id, morning_sections, evening_sections, updated_at)
        SELECT tenant_id, user_id, morning_sections, evening_sections, updated_at
        FROM report_preferences
        """,
        "DROP TABLE report_preferences",
        "ALTER TABLE report_preferences_v2 RENAME TO report_preferences",
        # Imported calendar events were unique on (source, external_id) alone.
        # Two companies syncing the same shared calendar — or two providers
        # that happen to mint the same id — would have collided, and the
        # second sync would have failed rather than kept its own copy. This
        # matters before any calendar connector is switched on, not after.
        "DROP INDEX idx_events_external",
        "CREATE UNIQUE INDEX idx_events_external "
        "ON events(tenant_id, user_id, source, external_id)",
    ),

    # Main executive-assistant capabilities rebased after the live SaaS v20 schema.
    (
            f"""
            CREATE TABLE memory_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX idx_memory_events_recent ON memory_events(user_id, created_at)",
            f"""
            CREATE TABLE memory_facts (
                fact_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                status TEXT NOT NULL DEFAULT 'active',
                confidence REAL NOT NULL DEFAULT 0.6,
                support_count INTEGER NOT NULL DEFAULT 1,
                importance REAL NOT NULL DEFAULT 0.5,
                decay_policy TEXT NOT NULL DEFAULT 'medium',
                source TEXT NOT NULL DEFAULT 'conversation',
                source_event_id TEXT REFERENCES memory_events(event_id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX idx_memory_facts_match
            ON memory_facts(user_id, subject, predicate, category, status)
            """,
            """
            CREATE INDEX idx_memory_facts_active
            ON memory_facts(user_id, status, last_seen_at)
            """,
            """
            CREATE TABLE memory_fact_observations (
                observation_id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL REFERENCES memory_facts(fact_id),
                event_id TEXT REFERENCES memory_events(event_id),
                observation_type TEXT NOT NULL,
                confidence_delta REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX idx_memory_observations_fact ON memory_fact_observations(fact_id)",
            """
            CREATE TABLE memory_fact_relations (
                relation_id TEXT PRIMARY KEY,
                from_fact_id TEXT NOT NULL REFERENCES memory_facts(fact_id),
                to_fact_id TEXT NOT NULL REFERENCES memory_facts(fact_id),
                relation_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX idx_memory_relations_from ON memory_fact_relations(from_fact_id)",
            "CREATE INDEX idx_memory_relations_to ON memory_fact_relations(to_fact_id)",
            # remove_diacritics 2 is not cosmetic here: without it "Lomé" and
            # "lome" are different tokens, and French queries silently miss.
            """
            CREATE VIRTUAL TABLE memory_facts_fts USING fts5(
                fact_id UNINDEXED,
                text,
                tokenize='unicode61 remove_diacritics 2'
            )
            """,
            """
            INSERT INTO memory_facts (
                fact_id, tenant_id, user_id, subject, predicate, object,
                category, status, confidence, support_count, importance,
                decay_policy, source, created_at, last_seen_at, updated_at
            )
            SELECT
                memory_id, tenant_id, user_id, 'utilisateur', 'note', content,
                category, 'active', 0.6, 1, 0.5,
                'medium', source, created_at, created_at, created_at
            FROM memories
            """,
            """
            INSERT INTO memory_facts_fts (fact_id, text)
            SELECT fact_id, subject || ' ' || predicate || ' ' || object || ' ' || category
            FROM memory_facts
            """,
            # Keep an immutable-shape copy for compatibility/privacy erasure,
            # while retaining ``memories`` for the Premium explicit-memory
            # surface. The factual kernel is canonical for extracted facts.
            f"""
            CREATE TABLE memories_v1_archive (
                memory_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                category TEXT NOT NULL DEFAULT 'fact',
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'conversation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            INSERT INTO memories_v1_archive
                (memory_id, tenant_id, user_id, category, content, source, created_at)
            SELECT memory_id, tenant_id, user_id, category, content, source, created_at
            FROM memories
            """,
        ),
    (),  # v22 reserved: SaaS users supersede the legacy singleton accounts table
    (
            f"""
            CREATE TABLE enabled_skills (
                skill_name TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                assistant_id TEXT NOT NULL DEFAULT '{DEFAULT_ASSISTANT_ID}',
                enabled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (assistant_id, skill_name)
            )
            """,
        ),
    (
            f"""
            CREATE TABLE usage_entries (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                scope TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX idx_usage_scope_day ON usage_entries(user_id, created_at, scope)",
        ),
    (
            f"""
            CREATE TABLE proactive_initiatives (
                initiative_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                assistant_id TEXT NOT NULL DEFAULT '{DEFAULT_ASSISTANT_ID}',
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                autonomy_level INTEGER NOT NULL DEFAULT 1,
                risk TEXT NOT NULL DEFAULT 'observe',
                status TEXT NOT NULL DEFAULT 'pending',
                dedupe_key TEXT NOT NULL DEFAULT '',
                cost_max_tokens INTEGER,
                deadline TEXT,
                payload TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            )
            """,
            """
            CREATE UNIQUE INDEX idx_proactive_initiatives_open_key
            ON proactive_initiatives(user_id, dedupe_key)
            WHERE status IN ('pending', 'approved', 'executing') AND dedupe_key <> ''
            """,
            "CREATE INDEX idx_proactive_initiatives_status ON proactive_initiatives(user_id, status, created_at)",
        ),
    (
            f"""
            CREATE TABLE missions (
                mission_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                goal TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned',
                conversation_id TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                max_tokens INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX idx_missions_status ON missions(user_id, status, created_at)",
            """
            CREATE TABLE mission_steps (
                step_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL REFERENCES missions(mission_id),
                position INTEGER NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL DEFAULT '{{}}',
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                result TEXT,
                verification TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE UNIQUE INDEX idx_mission_steps_order ON mission_steps(mission_id, position)",
        ),
    (
            "ALTER TABLE mission_steps ADD COLUMN success_criteria TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE missions ADD COLUMN strategy TEXT NOT NULL DEFAULT 'manual'",
            # Questions the planner could not answer from context. A mission with
            # open questions must not be executed as if it were complete.
            "ALTER TABLE missions ADD COLUMN missing_information TEXT NOT NULL DEFAULT '[]'",
        ),
    (
            f"""
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'business',
                status TEXT NOT NULL DEFAULT 'active',
                summary TEXT NOT NULL DEFAULT '',
                attributes TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # One entity per (kind, name). Without this, every mention of a client
            # creates a new node and the graph is worthless within a week.
            "CREATE UNIQUE INDEX idx_entities_identity ON entities(user_id, kind, slug)",
            "CREATE INDEX idx_entities_scope ON entities(user_id, scope, status)",
            """
            CREATE TABLE entity_relations (
                relation_id TEXT PRIMARY KEY,
                from_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
                to_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
                kind TEXT NOT NULL,
                attributes TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE UNIQUE INDEX idx_entity_relations_edge
            ON entity_relations(from_entity_id, to_entity_id, kind)
            """,
            "CREATE INDEX idx_entity_relations_to ON entity_relations(to_entity_id, kind)",
            """
            CREATE TABLE entity_timeline (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{tenant}',
                user_id TEXT NOT NULL DEFAULT '{user}',
                entity_id TEXT NOT NULL REFERENCES entities(entity_id),
                milestone TEXT NOT NULL DEFAULT 'note',
                headline TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                event_id TEXT REFERENCES memory_events(event_id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """.format(tenant=DEFAULT_TENANT_ID, user=DEFAULT_USER_ID),
            """
            CREATE INDEX idx_entity_timeline_entity
            ON entity_timeline(entity_id, occurred_at)
            """,
            # Facts can now belong to an entity. NULL means personal memory, which
            # is the existing behaviour and stays the default.
            "ALTER TABLE memory_facts ADD COLUMN entity_id TEXT REFERENCES entities(entity_id)",
            "CREATE INDEX idx_memory_facts_entity ON memory_facts(entity_id, status)",
        ),
    (
            f"""
            CREATE TABLE webauthn_credentials (
                credential_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
                account_id TEXT NOT NULL REFERENCES users(user_id),
                public_key TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                sign_count INTEGER NOT NULL DEFAULT 0,
                transports TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TEXT
            )
            """,
            "CREATE INDEX idx_webauthn_account ON webauthn_credentials(account_id)",
            # Challenges are single-use and short-lived; a replayed assertion must
            # not verify. Rows are consumed on use and swept by age.
            """
            CREATE TABLE webauthn_challenges (
                challenge TEXT PRIMARY KEY,
                account_id TEXT,
                purpose TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            # When the account's step-up happened on this browser. NULL means the
            # session has never presented the second factor.
            "ALTER TABLE devices ADD COLUMN second_factor_at TEXT",
        ),
    # 30 — ownership belongs to SaaS users, scoped to their tenant.  The old
    # main-v20 branch enforced a single owner globally in the legacy accounts
    # table; accounts are no longer an identity source.
    (
        "CREATE UNIQUE INDEX idx_users_tenant_owner "
        "ON users(tenant_id) WHERE role = 'owner'",
    ),
    # 31 — every uniqueness boundary that represents tenant-owned data must
    # include the tenant. Rebuild enabled_skills because SQLite cannot alter a
    # primary key in place; the other two constraints are ordinary indexes.
    (
        f"""
        CREATE TABLE enabled_skills_v31 (
            skill_name TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            assistant_id TEXT NOT NULL DEFAULT '{DEFAULT_ASSISTANT_ID}',
            enabled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, assistant_id, skill_name)
        )
        """,
        """
        INSERT OR IGNORE INTO enabled_skills_v31
            (skill_name, tenant_id, user_id, assistant_id, enabled_at)
        SELECT skill_name, tenant_id, user_id, assistant_id, enabled_at
        FROM enabled_skills
        """,
        "DROP TABLE enabled_skills",
        "ALTER TABLE enabled_skills_v31 RENAME TO enabled_skills",
        "DROP INDEX idx_proactive_initiatives_open_key",
        """
        CREATE UNIQUE INDEX idx_proactive_initiatives_open_key
        ON proactive_initiatives(tenant_id, user_id, dedupe_key)
        WHERE status IN ('pending', 'approved', 'executing') AND dedupe_key <> ''
        """,
        "DROP INDEX idx_entities_identity",
        """
        CREATE UNIQUE INDEX idx_entities_identity
        ON entities(tenant_id, user_id, kind, slug)
        """,
    ),
)


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _has_table(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _has_columns(
    connection: sqlite3.Connection, table: str, expected: set[str]
) -> bool:
    if not _has_table(connection, table):
        return False
    # The names below are internal migration constants, never user input.
    columns = {
        row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
    }
    return expected <= columns


def _migration_history(
    connection: sqlite3.Connection, applied: set[int]
) -> str:
    """Identify which of the two incompatible histories called itself v20."""
    is_recorded_v20 = applied == set(range(1, 21))
    if not is_recorded_v20:
        return "linear"

    has_main_memory = _has_columns(
        connection, "memory_events", {"event_id", "type", "source", "content"}
    )
    has_premium_crm = _has_columns(
        connection, "contacts", {"contact_id", "tenant_id", "user_id", "name"}
    )
    if has_main_memory and not has_premium_crm:
        return "main-v20"
    if has_premium_crm and not has_main_memory:
        return "premium-v20"
    return "linear"


def _converge_legacy_webauthn_identity(connection: sqlite3.Connection) -> None:
    """Move main-v20 account identities and credentials onto SaaS users.

    The historical branch made WebAuthn reference ``accounts(account_id)``.
    Premium made ``users(user_id)`` canonical.  Keep the legacy table for
    audit/recovery, but no active session or credential may depend on it.
    """
    if not _has_table(connection, "accounts"):
        return

    # A hand-edited historical database may contain an account whose user row
    # is missing (foreign-key enforcement was not enabled by the old connect
    # helper). Recreate that canonical identity before moving credentials.
    connection.execute(
        """
        INSERT OR IGNORE INTO users (
            user_id, tenant_id, display_name, email, password_hash, role,
            status, email_verified_at, last_login_at
        )
        SELECT a.user_id, a.tenant_id, a.display_name, a.email,
               a.password_hash, a.role, a.status, a.created_at, a.last_login_at
        FROM accounts a
        """
    )
    connection.execute(
        """
        UPDATE users
        SET email = (SELECT a.email FROM accounts a WHERE a.user_id = users.user_id),
            password_hash = (
                SELECT a.password_hash FROM accounts a WHERE a.user_id = users.user_id
            ),
            display_name = (
                SELECT a.display_name FROM accounts a WHERE a.user_id = users.user_id
            ),
            role = (SELECT a.role FROM accounts a WHERE a.user_id = users.user_id),
            status = (SELECT a.status FROM accounts a WHERE a.user_id = users.user_id),
            last_login_at = (
                SELECT a.last_login_at FROM accounts a WHERE a.user_id = users.user_id
            ),
            email_verified_at = COALESCE(
                email_verified_at,
                (SELECT a.created_at FROM accounts a WHERE a.user_id = users.user_id)
            )
        WHERE EXISTS (SELECT 1 FROM accounts a WHERE a.user_id = users.user_id)
        """
    )
    # Do not let the seeded placeholder compete with a separately identified
    # migrated owner in the default tenant's per-tenant unique index.
    connection.execute(
        """
        UPDATE users SET role = 'member'
        WHERE user_id = ? AND email = ''
          AND EXISTS (
              SELECT 1 FROM accounts a
              WHERE a.tenant_id = users.tenant_id
                AND a.user_id <> users.user_id
                AND a.role = 'owner'
          )
        """,
        (DEFAULT_USER_ID,),
    )

    if _has_columns(connection, "devices", {"account_id", "user_id"}):
        connection.execute(
            """
            UPDATE devices
            SET user_id = (
                SELECT a.user_id FROM accounts a WHERE a.account_id = devices.account_id
            )
            WHERE account_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM accounts a WHERE a.account_id = devices.account_id
              )
            """
        )

    if _has_table(connection, "webauthn_challenges"):
        connection.execute(
            """
            UPDATE webauthn_challenges
            SET account_id = (
                SELECT a.user_id FROM accounts a
                WHERE a.account_id = webauthn_challenges.account_id
            )
            WHERE EXISTS (
                SELECT 1 FROM accounts a
                WHERE a.account_id = webauthn_challenges.account_id
            )
            """
        )

    if not _has_table(connection, "webauthn_credentials"):
        return
    foreign_keys = connection.execute(
        'PRAGMA foreign_key_list("webauthn_credentials")'
    ).fetchall()
    if not any(row[2] == "accounts" for row in foreign_keys):
        return

    connection.execute("DROP INDEX IF EXISTS idx_webauthn_account")
    connection.execute(
        "ALTER TABLE webauthn_credentials RENAME TO webauthn_credentials_legacy"
    )
    legacy_credential_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM webauthn_credentials_legacy"
        ).fetchone()[0]
    )
    connection.execute(
        f"""
        CREATE TABLE webauthn_credentials (
            credential_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            account_id TEXT NOT NULL REFERENCES users(user_id),
            public_key TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            sign_count INTEGER NOT NULL DEFAULT 0,
            transports TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO webauthn_credentials (
            credential_id, tenant_id, account_id, public_key, label,
            sign_count, transports, created_at, last_used_at
        )
        SELECT wc.credential_id, u.tenant_id, a.user_id, wc.public_key, wc.label,
               wc.sign_count, wc.transports, wc.created_at, wc.last_used_at
        FROM webauthn_credentials_legacy wc
        JOIN accounts a ON a.account_id = wc.account_id
        JOIN users u ON u.user_id = a.user_id
        """
    )
    migrated_credential_count = int(
        connection.execute("SELECT COUNT(*) FROM webauthn_credentials").fetchone()[0]
    )
    if migrated_credential_count != legacy_credential_count:
        raise sqlite3.IntegrityError(
            "legacy WebAuthn credentials could not all be mapped to canonical users"
        )
    connection.execute("DROP TABLE webauthn_credentials_legacy")
    connection.execute(
        "CREATE INDEX idx_webauthn_account ON webauthn_credentials(account_id)"
    )


def run_migrations(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database_path)
    try:
        # BEGIN must precede even schema_migrations: SQLite DDL is transactional
        # only when it is enclosed in an explicit transaction.
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        applied = {
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

        if _migration_history(connection, applied) == "main-v20":
            # Production's versions 11-20 are today's 21-30.  Install the
            # missing Premium schema (today's 11-20), but never replay the main
            # DDL already present under its historical numbers.
            for statements in MIGRATIONS[10:20]:
                for statement in statements:
                    connection.execute(statement)

            # Both password identity and WebAuthn must now resolve through the
            # canonical SaaS users before the per-tenant owner index is added.
            _converge_legacy_webauthn_identity(connection)

            # v30 and every later migration are deliberately new and must be
            # applied to the converged production lineage as normal.
            for statements in MIGRATIONS[29:]:
                for statement in statements:
                    connection.execute(statement)
            for version in range(21, len(MIGRATIONS) + 1):
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
        else:
            # Use the full applied set rather than MAX(version), so a damaged
            # history with a gap does not silently skip that migration.
            for version, statements in enumerate(MIGRATIONS, start=1):
                if version in applied:
                    continue
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def schema_version(database_path: Path) -> int:
    with connect(database_path) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0
