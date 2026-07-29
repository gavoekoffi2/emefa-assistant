"""Roles are enforced by the server, on every route, or the build fails.

Two things are proved here.

1. **Coverage.** Every route the application actually registers has an entry
   in ``ROUTE_POLICY``. A new endpoint added without an authorisation
   decision fails this test rather than shipping open.
2. **Behaviour.** Each seat really is refused what its role does not grant,
   through the HTTP stack — not by reading the matrix back to itself.
"""

import asyncio

import httpx
import pytest
import pytest_asyncio

from emefa.api.authorization import ROUTE_POLICY, Access
from emefa.config import Settings
from emefa.domain.account_mail import Delivery
from emefa.domain.agent import AgentStep
from emefa.domain.roles import Permission
from emefa.main import create_app

ROLES = ("owner", "admin", "manager", "member", "viewer")


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


@pytest.fixture
def app(tmp_path):
    application = create_app(
        Settings(database_path=tmp_path / "permissions.db", cookie_secure=False),
        brain=Brain(),
    )
    application.state.account_mailer = Mailer()
    return application


def _registered_routes(app) -> set[tuple[str, str]]:
    """Walk the live application, including lazily-included routers."""
    found: set[tuple[str, str]] = set()

    def walk(routes, prefix=""):
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                walk(
                    route.original_router.routes,
                    prefix + getattr(route.include_context, "prefix", ""),
                )
                continue
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path is None or not methods:
                continue
            for method in methods - {"HEAD", "OPTIONS"}:
                found.add((method, prefix + path))

    walk(app.router.routes)
    return found


@pytest_asyncio.fixture
async def seats(app):
    """One signed-in session per role, all inside the same company."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        owner = await client.post(
            "/v1/auth/signup",
            json={
                "email": "jean@alpha.tg",
                "password": "motdepasse-solide",
                "display_name": "Jean",
                "company_name": "Entreprise Alpha",
            },
        )
        sessions = {"owner": {"Authorization": f"Bearer {owner.cookies['emefa_session']}"}}
        for role in ROLES[1:]:
            invited = await client.post(
                "/v1/auth/invitations",
                headers=sessions["owner"],
                json={"email": f"{role}@alpha.tg", "role": role},
            )
            assert invited.status_code == 201, invited.text
            token = app.state.account_mailer.invitations[f"{role}@alpha.tg"]
            joined = await client.post(
                "/v1/auth/invitations/accept",
                json={
                    "token": token,
                    "password": "motdepasse-solide",
                    "display_name": role,
                },
            )
            assert joined.status_code == 201, joined.text
            sessions[role] = {"Authorization": f"Bearer {joined.cookies['emefa_session']}"}
        yield client, sessions


# -- coverage --------------------------------------------------------------


def test_every_registered_route_has_an_authorisation_policy(app):
    """The whole point: you cannot add an endpoint and forget this."""
    missing = _registered_routes(app) - set(ROUTE_POLICY)
    assert not missing, (
        "these routes have no entry in ROUTE_POLICY and will be refused at "
        f"runtime: {sorted(missing)}. Decide what each one requires — leaving "
        "it out is not a way to make it public."
    )


def test_the_policy_table_has_no_entries_for_routes_that_no_longer_exist(app):
    """Dead entries hide the fact that a route was removed or renamed."""
    stale = set(ROUTE_POLICY) - _registered_routes(app)
    assert not stale, f"ROUTE_POLICY mentions routes that do not exist: {sorted(stale)}"


def test_the_public_surface_is_small_and_deliberate():
    """Anything reachable without a session is listed here on purpose."""
    public = {key for key, value in ROUTE_POLICY.items() if value is Access.PUBLIC}
    assert public == {
        ("GET", "/health"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
        ("POST", "/v1/auth/signup"),
        ("POST", "/v1/auth/signin"),
        ("POST", "/v1/auth/verify-email"),
        ("POST", "/v1/auth/password/forgot"),
        ("POST", "/v1/auth/password/reset"),
        ("GET", "/v1/auth/invitations/peek"),
        ("POST", "/v1/auth/invitations/accept"),
        ("POST", "/v1/devices/enroll"),
        ("POST", "/v1/web/session"),
    }, "the unauthenticated surface changed; that is a security decision"


def test_an_unclassified_route_is_refused_rather_than_allowed(app):
    """Fail closed. A route added without a policy must not be open."""
    from fastapi import APIRouter

    router = APIRouter(prefix="/v1/oubliee")

    @router.get("/secret")
    def secret() -> dict[str, str]:
        return {"leaked": "yes"}

    app.include_router(router)
    response = asyncio.run(_get(app, "/v1/oubliee/secret"))
    assert response.status_code == 403, "an unclassified route must fail closed"


async def _get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


# -- behaviour -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_viewer_can_read_the_business_but_change_nothing(seats):
    client, sessions = seats
    viewer = sessions["viewer"]

    assert (await client.get("/v1/crm/contacts", headers=viewer)).status_code == 200
    assert (await client.get("/v1/briefings/morning", headers=viewer)).status_code == 200

    refused = [
        await client.post(
            "/v1/crm/contacts", headers=viewer, json={"name": "X", "kind": "client"}
        ),
        await client.post("/v1/agenda", headers=viewer, json={
            "title": "Comité", "starts_at": "2026-08-03T10:00"}),
        await client.post("/v1/meetings", headers=viewer, json={"title": "Réunion"}),
        await client.post("/v1/agent/runs", headers=viewer, json={"message": "bonjour"}),
    ]
    assert [r.status_code for r in refused] == [403, 403, 403, 403]


@pytest.mark.asyncio
async def test_a_member_writes_but_does_not_delete(seats):
    client, sessions = seats
    member, owner = sessions["member"], sessions["owner"]

    created = await client.post(
        "/v1/crm/contacts", headers=member, json={"name": "Client du membre", "kind": "client"}
    )
    assert created.status_code == 201
    contact_id = created.json()["contact_id"]

    # Deleting the company's records is a manager decision.
    assert (await client.delete(
        f"/v1/crm/contacts/{contact_id}", headers=member
    )).status_code == 403
    assert (await client.delete(
        f"/v1/crm/contacts/{contact_id}", headers=sessions["manager"]
    )).status_code == 204
    # And it really was the manager's call that removed it.
    assert [c["name"] for c in (await client.get("/v1/crm/contacts", headers=owner)).json()] == []


@pytest.mark.asyncio
async def test_only_an_admin_or_owner_edits_the_company_profile(seats):
    client, sessions = seats
    for role in ("viewer", "member", "manager"):
        response = await client.patch(
            "/v1/assistant/business", headers=sessions[role], json={"industry": "Conseil"}
        )
        assert response.status_code == 403, role
    for role in ("admin", "owner"):
        response = await client.patch(
            "/v1/assistant/business", headers=sessions[role], json={"industry": "Conseil"}
        )
        assert response.status_code == 200, role


@pytest.mark.asyncio
async def test_only_an_admin_or_owner_manages_colleagues(seats):
    client, sessions = seats
    for role in ("viewer", "member", "manager"):
        assert (await client.get(
            "/v1/auth/invitations", headers=sessions[role]
        )).status_code == 403, role
        assert (await client.post(
            "/v1/auth/invitations", headers=sessions[role], json={"email": "x@alpha.tg"}
        )).status_code == 403, role
    assert (await client.get("/v1/auth/invitations", headers=sessions["admin"])).status_code == 200


@pytest.mark.asyncio
async def test_only_a_manager_or_above_creates_a_recurring_routine(seats):
    """A routine acts unattended, so it is a larger grant than a write."""
    client, sessions = seats
    payload = {"name": "Revue", "prompt": "Résume la semaine", "schedule_kind": "manual"}
    for role in ("viewer", "member"):
        assert (await client.post(
            "/v1/command-center/routines", headers=sessions[role], json=payload
        )).status_code == 403, role
    created = await client.post(
        "/v1/command-center/routines", headers=sessions["manager"], json=payload
    )
    assert created.status_code in (200, 201), created.text


@pytest.mark.asyncio
async def test_everyone_in_the_company_reads_the_same_crm(seats):
    """Roles restrict actions, not visibility: the CRM belongs to the company."""
    client, sessions = seats
    await client.post(
        "/v1/crm/contacts", headers=sessions["owner"],
        json={"name": "Client commun", "kind": "client"},
    )
    for role in ROLES:
        contacts = (await client.get("/v1/crm/contacts", headers=sessions[role])).json()
        assert [c["name"] for c in contacts] == ["Client commun"], role


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_reaches_nothing_but_the_public_surface(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for method, path in sorted(_registered_routes(app)):
            policy = ROUTE_POLICY[(method, path)]
            if policy in (Access.PUBLIC, Access.MACHINE) or "{" in path:
                continue
            response = await client.request(method, path, json={})
            assert response.status_code in (401, 403), (
                f"{method} {path} answered {response.status_code} with no session"
            )


def test_permissions_used_by_the_table_all_exist():
    """A typo in a permission name must not silently widen access."""
    for key, policy in ROUTE_POLICY.items():
        assert policy in (Access.PUBLIC, Access.ACCOUNT, Access.MACHINE) or isinstance(
            policy, Permission
        ), f"{key} has an unrecognised policy: {policy!r}"
