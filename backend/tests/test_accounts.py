"""Account authentication (ADR-002)."""

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.accounts import (
    AccountRepository,
    WeakPasswordError,
    hash_password,
    verify_password,
)
from emefa.domain.agent import AgentStep
from emefa.main import create_app

PASSWORD = "correct-horse-battery"


def build_app(tmp_path, name="auth.db"):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / name,
            cookie_secure=False,
        ),
        brain=Brain(),
    )


def test_password_hashes_are_salted_and_self_describing():
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second, "each hash must carry its own salt"
    assert first.startswith("scrypt$")
    assert verify_password(PASSWORD, first)
    assert not verify_password("mauvais mot de passe", first)
    # A corrupt or foreign hash fails closed rather than raising.
    assert not verify_password(PASSWORD, "bcrypt$whatever")
    assert not verify_password(PASSWORD, "n'importe quoi")


def test_short_passwords_are_refused_not_silently_accepted():
    with pytest.raises(WeakPasswordError):
        hash_password("court")


def test_repository_create_and_authenticate(tmp_path):
    accounts = AccountRepository(tmp_path / "repo.db")
    assert accounts.count() == 0

    account = accounts.create("  Koffi@Example.COM ", PASSWORD, "Koffi")
    assert account.email == "koffi@example.com", "addresses are normalised"
    assert account.role == "owner"
    assert accounts.count() == 1

    assert accounts.authenticate("KOFFI@example.com", PASSWORD) is not None
    assert accounts.authenticate("koffi@example.com", "mauvais") is None
    assert accounts.authenticate("inconnu@example.com", PASSWORD) is None
    assert accounts.get(account.account_id).last_login_at is not None

    with pytest.raises(ValueError):
        accounts.create("koffi@example.com", PASSWORD)
    with pytest.raises(ValueError):
        accounts.create("pas-une-adresse", PASSWORD)


def test_password_change_requires_the_current_one(tmp_path):
    accounts = AccountRepository(tmp_path / "change.db")
    account = accounts.create("koffi@example.com", PASSWORD)
    assert accounts.change_password(account.account_id, "mauvais", "nouveau-mot-secret") is False
    assert accounts.change_password(account.account_id, PASSWORD, "nouveau-mot-secret") is True
    assert accounts.authenticate("koffi@example.com", "nouveau-mot-secret") is not None
    assert accounts.authenticate("koffi@example.com", PASSWORD) is None


@pytest.mark.asyncio
async def test_registration_login_and_session_identity(tmp_path):
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        status = (await web.get("/v1/auth/status")).json()
        assert status == {"registered": False, "authenticated": False, "account": None}

        assert (await web.get("/v1/auth/me")).status_code == 401

        rejected = await web.post(
            "/v1/auth/register",
            json={
                "email": "koffi@example.com",
                "password": PASSWORD,
                "enrollment_code": "MAUVAIS",
            },
        )
        assert rejected.status_code == 403

        created = await web.post(
            "/v1/auth/register",
            json={
                "email": "koffi@example.com",
                "password": PASSWORD,
                "display_name": "Koffi",
                "enrollment_code": "CODE-SECRET",
            },
        )
        assert created.status_code == 201
        assert created.json()["email"] == "koffi@example.com"
        # Registration signs the browser in; the cookie is not readable by JS.
        cookie = created.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie

        status = (await web.get("/v1/auth/status")).json()
        assert status["registered"] is True
        assert status["authenticated"] is True
        assert status["account"]["display_name"] == "Koffi"

        assert (await web.get("/v1/auth/me")).json()["role"] == "owner"

        # The owner slot is taken; registration is not an open door.
        again = await web.post(
            "/v1/auth/register",
            json={
                "email": "autre@example.com",
                "password": PASSWORD,
                "enrollment_code": "CODE-SECRET",
            },
        )
        assert again.status_code == 409

        assert (await web.post("/v1/auth/logout")).status_code == 204
        assert (await web.get("/v1/auth/me")).status_code == 401

        assert (
            await web.post(
                "/v1/auth/login",
                json={"email": "koffi@example.com", "password": "mauvais"},
            )
        ).status_code == 401
        signed_in = await web.post(
            "/v1/auth/login",
            json={"email": "KOFFI@example.com", "password": PASSWORD},
        )
        assert signed_in.status_code == 200
        assert (await web.get("/v1/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_the_shared_code_stops_working_once_an_owner_exists(tmp_path):
    """The central security change: a shared secret must not reach a real
    account's data (ADR-002 §3)."""
    app = build_app(tmp_path, "bootstrap.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        # Before registration the bootstrap path works, as it always did.
        assert (
            await web.post(
                "/v1/web/session",
                json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
            )
        ).status_code == 201

        await web.post(
            "/v1/auth/register",
            json={
                "email": "koffi@example.com",
                "password": PASSWORD,
                "enrollment_code": "CODE-SECRET",
            },
        )

        refused = await web.post(
            "/v1/web/session",
            json={"name": "Autre navigateur", "enrollment_code": "CODE-SECRET"},
        )
        assert refused.status_code == 409
        enrolment = await web.post(
            "/v1/devices/enroll",
            json={"name": "Téléphone", "enrollment_code": "CODE-SECRET"},
        )
        assert enrolment.status_code == 409


@pytest.mark.asyncio
async def test_a_code_only_session_has_no_account_identity(tmp_path):
    """Sessions predating accounts keep working for the app, but they are not
    a principal: nothing can act as a named person on their behalf."""
    app = build_app(tmp_path, "legacy.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        assert (await web.get("/v1/memories")).status_code == 200
        assert (await web.get("/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_failed_logins_are_rate_limited(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "ratelimit.db",
            cookie_secure=False,
            activation_max_failures=3,
        ),
        brain=None,
    )
    AccountRepository(tmp_path / "ratelimit.db").create("koffi@example.com", PASSWORD)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        statuses = [
            (
                await web.post(
                    "/v1/auth/login",
                    json={"email": "koffi@example.com", "password": "mauvais"},
                )
            ).status_code
            for _ in range(5)
        ]
    assert 429 in statuses, "brute force must hit the limiter"


@pytest.mark.asyncio
async def test_password_change_over_http(tmp_path):
    app = build_app(tmp_path, "pwd.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/auth/register",
            json={
                "email": "koffi@example.com",
                "password": PASSWORD,
                "enrollment_code": "CODE-SECRET",
            },
        )
        wrong = await web.post(
            "/v1/auth/password",
            json={"current_password": "mauvais", "new_password": "un-autre-secret"},
        )
        assert wrong.status_code == 403

        changed = await web.post(
            "/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": "un-autre-secret"},
        )
        assert changed.status_code == 204

        await web.post("/v1/auth/logout")
        assert (
            await web.post(
                "/v1/auth/login",
                json={"email": "koffi@example.com", "password": "un-autre-secret"},
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_bootstrap_device_is_bound_and_other_unlinked_device_is_rejected(tmp_path):
    app = build_app(tmp_path, "device-boundary.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as current:
        assert (
            await current.post(
                "/v1/web/session",
                json={"name": "Courant", "enrollment_code": "CODE-SECRET"},
            )
        ).status_code == 201
        other = app.state.devices.enroll("Ancien téléphone")[1]
        assert (
            await current.post(
                "/v1/auth/register",
                json={
                    "email": "koffi@example.com",
                    "password": PASSWORD,
                    "enrollment_code": "CODE-SECRET",
                },
            )
        ).status_code == 201
        assert (await current.get("/v1/auth/me")).status_code == 200
        assert app.state.devices.count() == 2
        refused = await current.get(
            "/v1/memories", headers={"Authorization": f"Bearer {other}"}
        )
    assert refused.status_code == 401
    assert refused.json()["detail"] == "Account session required"


def test_first_owner_creation_is_atomic_under_race(tmp_path):
    accounts = AccountRepository(tmp_path / "owner-race.db")

    def create(index):
        try:
            return accounts.create_first_owner(f"owner{index}@example.com", PASSWORD).account_id
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, range(2)))
    assert sum(result is not None for result in results) == 1
    assert accounts.count() == 1


@pytest.mark.asyncio
async def test_password_change_revokes_other_devices_but_keeps_current(tmp_path):
    app = build_app(tmp_path, "pwd-devices.db")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as current:
        await current.post(
            "/v1/auth/register",
            json={
                "email": "koffi@example.com",
                "password": PASSWORD,
                "enrollment_code": "CODE-SECRET",
            },
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
            await other.post(
                "/v1/auth/login",
                json={"email": "koffi@example.com", "password": PASSWORD},
            )
            assert (await other.get("/v1/auth/me")).status_code == 200
            changed = await current.post(
                "/v1/auth/password",
                json={"current_password": PASSWORD, "new_password": "secret-rotation-2026"},
            )
            assert changed.status_code == 204
            assert (await current.get("/v1/auth/me")).status_code == 200
            assert (await other.get("/v1/auth/me")).status_code == 401
