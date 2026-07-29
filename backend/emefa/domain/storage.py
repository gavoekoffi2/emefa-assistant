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
    # 10 — governed command center: user-managed initiatives, routines and
    # auditable runs. This migration is intentionally compatible with the
    # schema already deployed by origin/main: production may already be v10.
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
    # 11 — memory kernel: atomic dated sourced facts (ADR-003).
    #
    # Replaces the flat `memories` table. The old rows are copied in as
    # unstructured `note` facts, keeping their identifiers so existing API
    # callers and stored references still resolve, then the old table is kept
    # under an archive name as the rollback path rather than dropped.
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
        "ALTER TABLE memories RENAME TO memories_v1_archive",
    ),
    # 12 — real accounts behind the device layer (ADR-002).
    #
    # Devices stay the transport credential; what they now carry is an
    # identity. Existing devices are bound to the seeded user by the default,
    # so an upgrade logs nobody out.
    (
        f"""
        CREATE TABLE accounts (
            account_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}'
                REFERENCES tenants(tenant_id),
            user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}'
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
    ),
    # 13 — per-assistant skill enablement.
    #
    # The catalogue itself is files on disk, versioned with the deployment. It
    # is deliberately not a table: what belongs in the database is the user's
    # decision about a skill, not the skill.
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
    # 14 — model usage accounting.
    #
    # Tokens are always recorded; money only when a price is configured. An
    # invented price is worse than no price: it produces a budget report the
    # owner would act on and that is quietly wrong.
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
    # 15 — governed proactive initiatives, distinct from the command center's
    # user-managed initiatives (different lifecycle, fields and public API).
    #
    # `dedupe_key` is unique among *open* initiatives only, enforced by a
    # partial index: a concern that persists for a week must produce one card,
    # but the same concern next month is a new one, and the closed history has
    # to survive for the audit.
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
    # 16 — durable missions.
    #
    # State is written after every step, which is the entire point: a mission
    # that only exists in a request's memory cannot survive a deploy, and a
    # step awaiting approval would hold a connection open until it timed out.
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
    # 17 — per-step success criteria, and how the plan was produced.
    #
    # A step without a stated success criterion can only be verified
    # structurally: "the call returned something". Writing down what success
    # means, at planning time, is what makes verification mean anything later.
    (
        "ALTER TABLE mission_steps ADD COLUMN success_criteria TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE missions ADD COLUMN strategy TEXT NOT NULL DEFAULT 'manual'",
        # Questions the planner could not answer from context. A mission with
        # open questions must not be executed as if it were complete.
        "ALTER TABLE missions ADD COLUMN missing_information TEXT NOT NULL DEFAULT '[]'",
    ),
    # 18 — the entity graph: projects, companies, people and what links them.
    #
    # Facts gain an owning entity, which is what separates business memory
    # from personal memory and makes "où en est le projet X" answerable by
    # lookup rather than by full-text luck.
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
    # 19 — WebAuthn second factor (ADR-005).
    #
    # No biometric data is stored here, and none ever reaches the server: a
    # credential is a public key. The face (or fingerprint) stays in the
    # device's secure enclave, which is precisely why this factor holds where
    # an in-browser embedding would not.
    (
        f"""
        CREATE TABLE webauthn_credentials (
            credential_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}',
            account_id TEXT NOT NULL REFERENCES accounts(account_id),
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
    # 20 — exactly one instance owner.  The partial unique index is the
    # database-level arbiter for concurrent bootstrap requests; an application
    # count/check can never make that guarantee on its own.
    (
        "CREATE UNIQUE INDEX idx_accounts_single_owner ON accounts(role) WHERE role = 'owner'",
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
        if current >= len(MIGRATIONS):
            return
        # Python's sqlite3 does not automatically open a transaction for DDL.
        # Without an explicit BEGIN, a process interruption can leave tables
        # created while the migration version is still old, making the next
        # startup retry fail on "table already exists".
        connection.execute("BEGIN IMMEDIATE")
        try:
            for version, statements in enumerate(MIGRATIONS[current:], start=current + 1):
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()


def schema_version(database_path: Path) -> int:
    with connect(database_path) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0
