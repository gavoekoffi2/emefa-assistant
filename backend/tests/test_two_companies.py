"""Entreprise Alpha and Entreprise Beta, through the real SaaS path.

The certification these tests exist to provide: nothing crosses between two
companies that both signed up on the same instance. Each of the six ways data
could cross gets its own test — lecture, modification, suppression,
recherche, export, référence — because "the CRM list looked right" is not
evidence about the other five.

Both companies are built the way a customer builds one: signup, invitations,
then real records. No repository is constructed directly and no scope is
passed by hand, so what is proved here is the behaviour of the deployed
request path rather than of the domain layer in isolation.
"""

from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.domain.account_mail import Delivery
from emefa.domain.agent import AgentStep
from emefa.main import create_app


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="ok")


class Mailer:
    def __init__(self):
        self.invitations: dict[str, str] = {}

    def send_verification(self, **_):
        return Delivery("email", True)

    def send_password_reset(self, **_):
        return Delivery("email", True)

    def send_invitation(self, *, to, token, **_):
        self.invitations[to] = token
        return Delivery("email", True)


@dataclass
class Company:
    """One tenant's identifiers, as seen from outside."""

    name: str
    tenant_id: str
    owner: dict[str, str]
    colleague: dict[str, str] = field(default_factory=dict)
    contact_id: str = ""
    project_id: str = ""
    deal_id: str = ""
    contract_id: str = ""
    document_id: str = ""
    task_title: str = ""


@pytest.fixture
def app(tmp_path):
    application = create_app(
        Settings(database_path=tmp_path / "two_companies.db", cookie_secure=False),
        brain=Brain(),
    )
    application.state.account_mailer = Mailer()
    return application


async def _build_company(client, app, *, name, owner_email, owner_name, slug) -> Company:
    """Sign up a company and fill it with a realistic book of business."""
    signup = await client.post(
        "/v1/auth/signup",
        json={
            "email": owner_email,
            "password": "motdepasse-solide",
            "display_name": owner_name,
            "company_name": name,
        },
    )
    assert signup.status_code == 201, signup.text
    owner = {"Authorization": f"Bearer {signup.cookies['emefa_session']}"}
    company = Company(name=name, tenant_id=signup.json()["tenant_id"], owner=owner)

    # A colleague, so "the company" is more than one person.
    invited = await client.post(
        "/v1/auth/invitations",
        headers=owner,
        json={"email": f"collegue@{slug}.tg", "role": "manager"},
    )
    assert invited.status_code == 201, invited.text
    joined = await client.post(
        "/v1/auth/invitations/accept",
        json={
            "token": app.state.account_mailer.invitations[f"collegue@{slug}.tg"],
            "password": "motdepasse-solide",
            "display_name": f"Collègue {name}",
        },
    )
    assert joined.status_code == 201, joined.text
    company.colleague = {"Authorization": f"Bearer {joined.cookies['emefa_session']}"}

    contact = await client.post(
        "/v1/crm/contacts",
        headers=owner,
        json={"name": f"Client {name}", "kind": "client", "email": f"client@{slug}.tg"},
    )
    company.contact_id = contact.json()["contact_id"]

    project = await client.post(
        "/v1/crm/projects",
        headers=owner,
        json={
            "name": f"Projet {name}",
            "contact_id": company.contact_id,
            "status": "en_cours",
        },
    )
    assert project.status_code == 201, project.text
    company.project_id = project.json()["project_id"]

    deal = await client.post(
        "/v1/crm/deals",
        headers=owner,
        json={
            "title": f"Devis {name}",
            "contact_id": company.contact_id,
            "amount": 750_000,
            "stage": "envoyé",
        },
    )
    company.deal_id = deal.json()["deal_id"]

    contract = await client.post(
        "/v1/crm/contracts",
        headers=owner,
        json={
            "title": f"Contrat {name}",
            "contact_id": company.contact_id,
            "end_date": "2026-12-31",
            "status": "actif",
        },
    )
    company.contract_id = contract.json()["contract_id"]

    # A meeting produces minutes (a real .docx) and a task.
    company.task_title = f"Action {name}"
    meeting = await client.post(
        "/v1/meetings",
        headers=owner,
        json={
            "title": f"Comité {name}",
            "participants": [owner_name],
            "decisions": [f"Décision {name}"],
            "actions": [{"description": company.task_title, "owner": "moi"}],
            "project": f"Projet {name}",
        },
    )
    assert meeting.status_code in (200, 201), meeting.text
    company.document_id = meeting.json()["document"]["document_id"]

    await client.post(
        "/v1/agenda",
        headers=owner,
        json={"title": f"Rendez-vous {name}", "starts_at": "2026-08-03T10:00"},
    )
    return company


@pytest_asyncio.fixture
async def companies(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        alpha = await _build_company(
            client, app, name="Entreprise Alpha",
            owner_email="jean@alpha.tg", owner_name="Jean", slug="alpha",
        )
        beta = await _build_company(
            client, app, name="Entreprise Beta",
            owner_email="amina@beta.tg", owner_name="Amina", slug="beta",
        )
        assert alpha.tenant_id != beta.tenant_id
        yield client, alpha, beta


def _pairs(alpha: Company, beta: Company):
    """Each company paired with the one it must not be able to reach."""
    return ((alpha, beta), (beta, alpha))


# -- 1. lecture ------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_list_endpoint_returns_the_other_company_s_records(companies):
    client, alpha, beta = companies
    collections = (
        "/v1/crm/contacts", "/v1/crm/projects", "/v1/crm/deals",
        "/v1/crm/contracts", "/v1/crm/interactions", "/v1/tasks",
        "/v1/meetings", "/v1/documents", "/v1/prospects",
    )
    for mine, theirs in _pairs(alpha, beta):
        for path in collections:
            body = (await client.get(path, headers=mine.owner)).text
            assert theirs.name not in body, f"{theirs.name} leaked into {path} for {mine.name}"


@pytest.mark.asyncio
async def test_reading_a_record_by_id_across_companies_returns_nothing(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        meeting = await client.get(f"/v1/meetings/{theirs.document_id}", headers=mine.owner)
        assert meeting.status_code == 404
        agenda = await client.get(
            f"/v1/agenda/{theirs.project_id}/preparation", headers=mine.owner
        )
        assert agenda.status_code == 404


@pytest.mark.asyncio
async def test_the_briefings_never_mention_the_other_company(companies):
    """The report is composed from many repositories at once — one unscoped
    read anywhere in it would show up here."""
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        for path in ("/v1/briefings/morning", "/v1/briefings/evening"):
            text = (await client.get(path, headers=mine.owner)).json()["text"]
            assert theirs.name not in text, f"{theirs.name} in {mine.name}'s {path}"
            assert theirs.task_title not in text
            assert mine.name in text or mine.task_title in text, "own data must still appear"


@pytest.mark.asyncio
async def test_the_command_centre_snapshot_counts_only_one_company(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        snapshot = (await client.get("/v1/command-center/snapshot", headers=mine.owner)).text
        assert theirs.name not in snapshot


@pytest.mark.asyncio
async def test_a_colleague_sees_their_own_company_and_not_the_other(companies):
    """Isolation is per company, not per person: the colleague sees the same
    book of business as their owner, and still nothing of the other."""
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        contacts = (await client.get("/v1/crm/contacts", headers=mine.colleague)).json()
        assert [c["name"] for c in contacts] == [f"Client {mine.name}"]


# -- 2. modification -------------------------------------------------------


@pytest.mark.asyncio
async def test_no_record_of_one_company_can_be_modified_by_the_other(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        attempts = {
            f"/v1/crm/contacts/{theirs.contact_id}": {"notes": "modifié"},
            f"/v1/crm/projects/{theirs.project_id}": {"status": "annulé"},
            f"/v1/crm/deals/{theirs.deal_id}": {"stage": "perdu"},
            f"/v1/crm/contracts/{theirs.contract_id}": {"status": "résilié"},
        }
        for path, payload in attempts.items():
            response = await client.patch(path, headers=mine.owner, json=payload)
            assert response.status_code in (404, 422), (path, response.status_code)

    # And nothing actually changed.
    for company in (alpha, beta):
        contact = (await client.get("/v1/crm/contacts", headers=company.owner)).json()[0]
        assert contact["notes"] == ""
        deal = (await client.get("/v1/crm/deals", headers=company.owner)).json()[0]
        assert deal["stage"] == "envoyé"


# -- 3. suppression --------------------------------------------------------


@pytest.mark.asyncio
async def test_no_record_of_one_company_can_be_deleted_by_the_other(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        for path in (
            f"/v1/crm/contacts/{theirs.contact_id}",
            f"/v1/crm/projects/{theirs.project_id}",
            f"/v1/crm/deals/{theirs.deal_id}",
            f"/v1/crm/contracts/{theirs.contract_id}",
            f"/v1/meetings/{theirs.document_id}",
        ):
            response = await client.delete(path, headers=mine.owner)
            assert response.status_code == 404, (path, response.status_code)

    # Everything survived.
    for company in (alpha, beta):
        for path in ("/v1/crm/contacts", "/v1/crm/projects", "/v1/crm/deals", "/v1/crm/contracts"):
            assert len((await client.get(path, headers=company.owner)).json()) == 1, path


# -- 4. recherche ----------------------------------------------------------


@pytest.mark.asyncio
async def test_search_never_finds_the_other_company_s_records(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        for query in (theirs.name, f"Client {theirs.name}", f"Projet {theirs.name}"):
            found = (await client.get(
                "/v1/crm/lookup", headers=mine.owner, params={"query": query}
            )).json()
            assert found["found"] is False, f"{mine.name} found {query!r}"


@pytest.mark.asyncio
async def test_a_name_shared_by_both_companies_resolves_to_the_caller_s_own(companies):
    """The dangerous case: identical names on both sides. Neither must see an
    ambiguity, and each must resolve to their own record."""
    client, alpha, beta = companies
    for company in (alpha, beta):
        await client.post(
            "/v1/crm/contacts", headers=company.owner,
            json={"name": "Horizon Group", "kind": "client",
                  "notes": f"appartient à {company.name}"},
        )
    for company in (alpha, beta):
        found = (await client.get(
            "/v1/crm/lookup", headers=company.owner, params={"query": "Horizon"}
        )).json()
        assert found["found"] is True
        assert found["contact"]["notes"] == f"appartient à {company.name}"


# -- 5. export -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_document_cannot_be_downloaded_across_companies(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        stolen = await client.get(
            f"/v1/documents/{theirs.document_id}/download", headers=mine.owner
        )
        assert stolen.status_code == 404
        own = await client.get(
            f"/v1/documents/{mine.document_id}/download", headers=mine.owner
        )
        assert own.status_code == 200
        assert own.content[:2] == b"PK", "a real .docx, not an error page"


@pytest.mark.asyncio
async def test_the_memory_export_contains_one_company_only(companies):
    client, alpha, beta = companies
    for company in (alpha, beta):
        await client.post(
            "/v1/agent/runs", headers=company.owner,
            json={"message": f"Retiens que {company.name} livre le vendredi"},
        )
    for mine, theirs in _pairs(alpha, beta):
        export = (await client.get("/v1/memories/export", headers=mine.owner)).text
        assert theirs.name not in export


@pytest.mark.asyncio
async def test_documents_are_stored_in_separate_directories(app, companies):
    """Filesystem isolation, not only SQL: one tenant's folder must not
    contain another's deliverables."""
    _, alpha, beta = companies
    root = app.state.settings.database_path.parent / "documents"
    directories = {path.name for path in root.iterdir() if path.is_dir()}
    assert alpha.tenant_id in directories and beta.tenant_id in directories
    for company, other in _pairs(alpha, beta):
        names = " ".join(p.name for p in (root / company.tenant_id).iterdir())
        assert other.tenant_id not in names


# -- 6. référence ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_record_cannot_reference_the_other_company_s_records(companies):
    """The subtle one. Reads are filtered, but a *write* that points at a
    foreign id would knit the two companies together through a join."""
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        smuggled = await client.post(
            "/v1/crm/deals",
            headers=mine.owner,
            json={
                "title": "Devis passe-frontière",
                "contact_id": theirs.contact_id,
                "amount": 1,
                "stage": "envoyé",
            },
        )
        assert smuggled.status_code in (404, 422), smuggled.status_code

        project = await client.post(
            "/v1/crm/projects",
            headers=mine.owner,
            json={"name": "Projet passe-frontière", "contact_id": theirs.contact_id},
        )
        assert project.status_code in (404, 422), project.status_code

    # No orphan rows were created by the attempts.
    for company in (alpha, beta):
        deals = (await client.get("/v1/crm/deals", headers=company.owner)).json()
        assert [d["title"] for d in deals] == [f"Devis {company.name}"]


@pytest.mark.asyncio
async def test_a_meeting_cannot_be_attached_to_the_other_company_s_project(companies):
    client, alpha, beta = companies
    for mine, theirs in _pairs(alpha, beta):
        response = await client.post(
            "/v1/meetings",
            headers=mine.owner,
            json={
                "title": "Comité détourné",
                "summary": "tentative",
                "project": f"Projet {theirs.name}",
            },
        )
        # Either refused, or accepted without linking anything — never linked.
        if response.status_code in (200, 201):
            assert not response.json().get("project_updated"), (
                f"{mine.name} attached a meeting to {theirs.name}'s project"
            )


# -- the assistant itself --------------------------------------------------


@pytest.mark.asyncio
async def test_the_assistant_answers_from_the_caller_s_company_only(app, companies):
    """The tool shelf is built per workspace; a shared one would leak here."""
    _, alpha, beta = companies
    from emefa.domain.scope import Scope

    for mine, theirs in _pairs(alpha, beta):
        members = app.state.accounts.list_members(mine.tenant_id)
        shelf = app.state.workspace_for(
            Scope(mine.tenant_id, members[0].user_id)
        ).agent.tools
        assert shelf.get("crm_overview").handler({})["counts"]["contacts"] == 1
        assert shelf.get("crm_lookup").handler({"query": theirs.name})["found"] is False
        assert shelf.get("crm_lookup").handler({"query": mine.name})["found"] is True


@pytest.mark.asyncio
async def test_each_company_has_its_own_assistant_and_profile(companies):
    client, alpha, beta = companies
    profiles = {}
    for company in (alpha, beta):
        await client.patch(
            "/v1/assistant/business", headers=company.owner,
            json={"company_name": company.name, "offer": f"offre de {company.name}"},
        )
        profiles[company.name] = (
            await client.get("/v1/assistant/business", headers=company.owner)
        ).json()

    assert profiles[alpha.name]["assistant_id"] != profiles[beta.name]["assistant_id"]
    for mine, theirs in _pairs(alpha, beta):
        assert profiles[mine.name]["offer"] == f"offre de {mine.name}"
        assert theirs.name not in profiles[mine.name]["offer"]
