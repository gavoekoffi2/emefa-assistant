"""Two tenants must not see each other's business data.

ADR-003 delivered credential isolation and recorded that everything else was
still single-scope. These tests cover the repositories that have since been
scoped, and — just as importantly — the conformance test at the bottom keeps an
honest, executable list of the ones that have **not**, so the gap can shrink
but never silently grow.
"""

import pytest

from emefa.domain import storage
from emefa.domain.agenda import AgendaRepository
from emefa.domain.crm import CrmRepository
from emefa.domain.memories import MemoryRepository
from emefa.domain.scope import DEFAULT_SCOPE, Scope, ScopedStore
from emefa.domain.tasks import TaskRepository

JEAN = Scope(tenant_id="ten_a", user_id="usr_jean")
AMINA = Scope(tenant_id="ten_b", user_id="usr_amina")

#: Repositories whose rows are filtered by tenant and user today.
SCOPED_REPOSITORIES = (CrmRepository, TaskRepository, MemoryRepository, AgendaRepository)

#: The identity tables themselves. They carry tenant_id because they *define*
#: the hierarchy, not because they are data owned within it.
IDENTITY_TABLES = ("tenants", "users")

#: Still single-scope. Listed so the gap is visible in the test suite rather
#: than only in a document; move a name up as it gets scoped.
KNOWN_UNSCOPED_TABLES = (
    "meetings", "meeting_decisions", "meeting_actions",
    "prospects", "initiatives", "routines", "routine_runs",
    "briefings", "evening_reports", "report_preferences",
    "conversation_turns", "pending_actions", "uploaded_files",
    "artifacts", "onboarding_state", "business_profiles", "assistants",
)


@pytest.fixture
def two_tenants(tmp_path):
    database = tmp_path / "tenants.db"
    return (
        database,
        {
            "crm": CrmRepository(database, JEAN),
            "tasks": TaskRepository(database, JEAN),
            "memories": MemoryRepository(database, JEAN),
        },
        {
            "crm": CrmRepository(database, AMINA),
            "tasks": TaskRepository(database, AMINA),
            "memories": MemoryRepository(database, AMINA),
        },
    )


def test_the_crm_of_one_tenant_is_invisible_to_the_other(two_tenants):
    _, jean, amina = two_tenants
    jean_client = jean["crm"].save_contact(name="Horizon Group", kind="client")
    amina_client = amina["crm"].save_contact(name="Sahel Distribution", kind="client")

    assert [c.name for c in jean["crm"].list_contacts()] == ["Horizon Group"]
    assert [c.name for c in amina["crm"].list_contacts()] == ["Sahel Distribution"]

    # A direct read by id across the boundary returns nothing.
    assert jean["crm"].get_contact(amina_client.contact_id) is None
    assert amina["crm"].get_contact(jean_client.contact_id) is None


def test_one_tenant_cannot_modify_or_delete_the_other_s_records(two_tenants):
    _, jean, amina = two_tenants
    amina_client = amina["crm"].save_contact(name="Sahel Distribution", kind="client")

    # Updating someone else's row is refused as "not found", not silently applied.
    from emefa.domain.crm import CrmError

    with pytest.raises(CrmError):
        jean["crm"].save_contact(amina_client.contact_id, notes="modifié par Jean")
    assert amina["crm"].get_contact(amina_client.contact_id).notes == ""

    assert jean["crm"].delete_contact(amina_client.contact_id) is False
    assert amina["crm"].get_contact(amina_client.contact_id) is not None


def test_name_resolution_never_reaches_across_tenants(two_tenants):
    """The ambiguity guard must not be confused by another tenant's records."""
    _, jean, amina = two_tenants
    jean["crm"].save_contact(name="Horizon Group", kind="client")
    amina["crm"].save_contact(name="Horizon Logistics", kind="client")

    # Two "Horizon" rows exist in the file, one per tenant — so neither owner
    # sees an ambiguity, and each resolves to their own.
    resolved = jean["crm"].resolve_contact("Horizon")
    assert jean["crm"].get_contact(resolved).name == "Horizon Group"
    assert amina["crm"].get_contact(amina["crm"].resolve_contact("Horizon")).name == (
        "Horizon Logistics"
    )


def test_tasks_and_memories_are_separated(two_tenants):
    _, jean, amina = two_tenants
    jean_task = jean["tasks"].create("Signer le contrat Horizon")
    amina["tasks"].create("Préparer l'inventaire")
    jean["memories"].remember("Jean préfère les réponses courtes")
    amina["memories"].remember("Amina travaille le samedi")

    assert [t.title for t in jean["tasks"].list_open()] == ["Signer le contrat Horizon"]
    assert [t.title for t in amina["tasks"].list_open()] == ["Préparer l'inventaire"]
    assert jean["tasks"].get(jean_task.task_id) is not None
    assert amina["tasks"].get(jean_task.task_id) is None
    # Completing another tenant's task does nothing.
    assert amina["tasks"].complete(jean_task.task_id) is None
    assert jean["tasks"].get(jean_task.task_id).status == "open"

    assert [m.content for m in jean["memories"].list_all()] == [
        "Jean préfère les réponses courtes"
    ]
    assert "Amina" not in jean["memories"].context_block()


def test_the_agenda_is_separated_including_conflict_detection(tmp_path):
    database = tmp_path / "agenda.db"
    jean = AgendaRepository(database, CrmRepository(database, JEAN), None, JEAN)
    amina = AgendaRepository(database, CrmRepository(database, AMINA), None, AMINA)

    jean.save_event(title="Comité", starts_at="2026-08-03T10:00", ends_at="2026-08-03T11:30")
    amina.save_event(title="Inventaire", starts_at="2026-08-03T11:00", ends_at="2026-08-03T12:00")

    from datetime import date

    day = date(2026, 8, 3)
    assert [e.title for e in jean.day(day)] == ["Comité"]
    assert [e.title for e in amina.day(day)] == ["Inventaire"]
    # The two meetings overlap in wall-clock time but belong to different
    # people, so neither is told they have a clash.
    assert jean.conflicts(day) == []
    assert amina.conflicts(day) == []


def test_a_repository_can_be_rebound_to_another_scope(tmp_path):
    """`for_scope` is how a request resolves its own owner's data."""
    database = tmp_path / "rebind.db"
    crm = CrmRepository(database, JEAN)
    crm.save_contact(name="Horizon Group", kind="client")

    assert len(crm.for_scope(AMINA).list_contacts()) == 0
    assert len(crm.for_scope(JEAN).list_contacts()) == 1
    # The original is unchanged: rebinding returns a sibling, not a mutation.
    assert crm.scope == JEAN


def test_existing_single_tenant_data_keeps_working(tmp_path):
    """The deployed instance runs as the default scope and must not notice."""
    database = tmp_path / "default.db"
    crm = CrmRepository(database)
    assert crm.scope == DEFAULT_SCOPE
    crm.save_contact(name="Ama Mensah", kind="client")
    # Rows created before scoping carry the default owner, so they stay visible.
    assert [c.name for c in CrmRepository(database).list_contacts()] == ["Ama Mensah"]


def test_scoped_stores_cannot_express_an_unscoped_query(tmp_path):
    """The interface itself is the guarantee: no method omits the scope."""
    from emefa.domain.scope import Ownership

    store = ScopedStore(tmp_path / "shape.db", JEAN)
    sql = store._scoped_sql("*", "contacts", "kind = ?", "LIMIT 1")
    assert "tenant_id = ?" in sql
    assert sql.index("tenant_id") < sql.index("kind"), "scope must lead the predicate"
    # Even with no caller predicate, the scope is still applied.
    assert "WHERE tenant_id = ?" in store._scoped_sql("*", "contacts", "", "")
    # A personal table also carries the user.
    personal = store._scoped_sql("*", "events", "", "", Ownership.USER)
    assert "WHERE tenant_id = ? AND user_id = ?" in personal


def test_the_unscoped_tables_are_the_ones_we_think_they_are(tmp_path):
    """A conformance check, not a rubber stamp.

    Every table carrying ``tenant_id`` is either scoped by a repository above
    or listed as a known gap. A new table added without scoping fails here,
    which is the only way this list shrinks instead of quietly growing.
    """
    database = tmp_path / "conformance.db"
    storage.run_migrations(database)
    with storage.connect(database) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        tenant_tables = {
            table for table in tables
            if any(
                column[1] == "tenant_id"
                for column in connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
        }

    scoped_now = {
        "contacts", "projects", "deals", "contracts", "interactions",
        "tasks", "memories", "events", "connected_accounts",
    }
    unaccounted = (
        tenant_tables - scoped_now - set(KNOWN_UNSCOPED_TABLES) - set(IDENTITY_TABLES)
    )
    assert not unaccounted, (
        f"these tables carry tenant_id but are neither scoped nor listed as a known "
        f"gap: {sorted(unaccounted)}. Scope them, or add them to "
        f"KNOWN_UNSCOPED_TABLES with intent."
    )
    # And the ones we claim are scoped really do exist.
    assert scoped_now <= tenant_tables


def test_every_scoped_repository_accepts_and_honours_a_scope(tmp_path):
    for repository in SCOPED_REPOSITORIES:
        instance = repository(tmp_path / "signature.db", scope=JEAN) if repository is not AgendaRepository \
            else repository(tmp_path / "signature.db", None, None, JEAN)
        assert isinstance(instance, ScopedStore)
        assert instance.scope == JEAN


# -- the request path ------------------------------------------------------


@pytest.fixture
def two_tenant_app(tmp_path):
    """An instance with two enrolled owners, as a real deployment would have."""
    import httpx

    from emefa.config import Settings
    from emefa.domain.agent import AgentStep
    from emefa.main import create_app

    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="ok")

    database = tmp_path / "api.db"
    app = create_app(Settings(database_path=database), brain=Brain())
    _, jean_token = app.state.devices.enroll("Poste de Jean")
    _, amina_token = app.state.devices.enroll("Poste d'Amina")
    with storage.connect(database) as connection:
        connection.execute("INSERT INTO tenants (tenant_id, name) VALUES ('ten_b', 'Amina SARL')")
        connection.execute(
            "INSERT INTO users (user_id, tenant_id, display_name) "
            "VALUES ('usr_amina', 'ten_b', 'Amina')"
        )
        connection.execute(
            "UPDATE devices SET user_id = 'usr_amina' WHERE name = ?", ("Poste d'Amina",)
        )
    return app, httpx.ASGITransport(app=app), (
        {"Authorization": f"Bearer {jean_token}"},
        {"Authorization": f"Bearer {amina_token}"},
    )


@pytest.mark.asyncio
async def test_the_api_serves_each_owner_only_their_own_data(two_tenant_app):
    """Regression guard: scoped repositories are not enough on their own.

    The repositories were scoped before the request path was, so the API kept
    serving one startup-built instance and Jean saw Amina's contacts. Anything
    that resolves through application state instead of the caller's workspace
    reintroduces exactly that.
    """
    import httpx

    _, transport, (jean, amina) = two_tenant_app
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/crm/contacts", headers=jean, json={"name": "Horizon Group", "kind": "client"}
        )
        contact_id = created.json()["contact_id"]
        await client.post(
            "/v1/crm/contacts", headers=amina,
            json={"name": "Sahel Distribution", "kind": "client"},
        )
        await client.post("/v1/agenda", headers=jean,
                          json={"title": "Comité Jean", "starts_at": "2026-08-03T10:00"})
        await client.post("/v1/meetings", headers=jean,
                          json={"title": "Réunion Jean",
                                "actions": [{"description": "Tâche de Jean", "owner": "moi"}]})
        await client.post("/v1/meetings", headers=amina,
                          json={"title": "Réunion Amina",
                                "actions": [{"description": "Tâche d'Amina", "owner": "moi"}]})

        jean_contacts = (await client.get("/v1/crm/contacts", headers=jean)).json()
        amina_contacts = (await client.get("/v1/crm/contacts", headers=amina)).json()
        assert [c["name"] for c in jean_contacts] == ["Horizon Group"]
        assert [c["name"] for c in amina_contacts] == ["Sahel Distribution"]

        # Reaching across by id is refused, not silently applied.
        stolen = await client.patch(
            f"/v1/crm/contacts/{contact_id}", headers=amina, json={"notes": "vol"}
        )
        assert stolen.status_code == 422
        assert (await client.delete(
            f"/v1/crm/contacts/{contact_id}", headers=amina
        )).status_code == 404

        jean_tasks = [t["title"] for t in (await client.get("/v1/tasks", headers=jean)).json()]
        amina_tasks = [t["title"] for t in (await client.get("/v1/tasks", headers=amina)).json()]
        assert jean_tasks == ["Tâche de Jean"]
        assert amina_tasks == ["Tâche d'Amina"]

        assert len((await client.get("/v1/agenda", headers=jean)).json()["upcoming"]) == 1
        assert (await client.get("/v1/agenda", headers=amina)).json()["upcoming"] == []

        jean_brief = (await client.get("/v1/briefings/morning", headers=jean)).json()["text"]
        amina_brief = (await client.get("/v1/briefings/morning", headers=amina)).json()["text"]
        assert "Tâche de Jean" in jean_brief and "Tâche d'Amina" not in jean_brief
        assert "Tâche d'Amina" in amina_brief and "Tâche de Jean" not in amina_brief

        # And the assistant answers from the caller's data, not the instance's.
        blind = await client.get("/v1/crm/lookup", headers=jean, params={"query": "Sahel"})
        assert blind.json()["found"] is False


@pytest.mark.asyncio
async def test_the_agent_runs_against_the_callers_workspace(two_tenant_app):
    """The tool shelf must be built on the caller's repositories."""
    app, transport, (jean, amina) = two_tenant_app
    import httpx

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/v1/crm/contacts", headers=jean,
                          json={"name": "Horizon Group", "kind": "client"})
        await client.post("/v1/crm/contacts", headers=amina,
                          json={"name": "Sahel Distribution", "kind": "client"})

    jean_scope = Scope(storage.DEFAULT_TENANT_ID, storage.DEFAULT_USER_ID)
    amina_scope = Scope("ten_b", "usr_amina")
    jean_shelf = app.state.workspace_for(jean_scope).agent.tools
    amina_shelf = app.state.workspace_for(amina_scope).agent.tools

    jean_seen = jean_shelf.get("crm_overview").handler({})["counts"]["contacts"]
    amina_seen = amina_shelf.get("crm_overview").handler({})["counts"]["contacts"]
    assert jean_seen == 1 and amina_seen == 1
    assert jean_shelf.get("crm_lookup").handler({"query": "Sahel"})["found"] is False
    assert amina_shelf.get("crm_lookup").handler({"query": "Sahel"})["found"] is True

    # The single-tenant deployment keeps one object identity.
    assert app.state.workspace_for(jean_scope).agent is app.state.agent
