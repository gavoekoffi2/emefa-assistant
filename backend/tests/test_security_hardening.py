import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.domain.devices import DeviceRepository
from emefa.domain.ratelimit import FailureLimiter
from emefa.main import create_app


@pytest_asyncio.fixture
async def client(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "hardening.db",
            cookie_secure=False,
            activation_max_failures=3,
            activation_window_seconds=60,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def test_limiter_blocks_after_max_failures_and_recovers():
    now = [0.0]
    limiter = FailureLimiter(max_failures=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.allow("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")
    now[0] = 11.0
    assert limiter.allow("1.2.3.4")


def test_limiter_global_bucket_bounds_distributed_attempts():
    limiter = FailureLimiter(max_failures=2, window_seconds=10, global_max_failures=3)
    for index in range(3):
        limiter.record_failure(f"10.0.0.{index}")
    assert not limiter.allow("10.0.0.99")


@pytest.mark.asyncio
async def test_activation_lockout_after_repeated_bad_codes(client):
    for _ in range(3):
        response = await client.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "FAUX"},
        )
        assert response.status_code == 403
    locked = await client.post(
        "/v1/web/session",
        json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_enroll_shares_the_same_lockout(client):
    for _ in range(3):
        await client.post(
            "/v1/devices/enroll",
            json={"name": "Téléphone", "enrollment_code": "FAUX"},
        )
    locked = await client.post(
        "/v1/devices/enroll",
        json={"name": "Téléphone", "enrollment_code": "CODE-SECRET"},
    )
    assert locked.status_code == 429


@pytest.mark.asyncio
async def test_expired_session_token_is_rejected_and_purged(client, tmp_path):
    activated = await client.post(
        "/v1/web/session",
        json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
    )
    assert activated.status_code == 201
    repository = DeviceRepository(tmp_path / "hardening.db")
    with repository._connect() as connection:
        connection.execute("UPDATE devices SET created_at = '2000-01-01 00:00:00'")
    status = await client.get("/v1/web/session")
    assert status.status_code == 401
    assert repository.count() == 0


def test_token_stays_valid_without_max_age(tmp_path):
    repository = DeviceRepository(tmp_path / "no-expiry.db")
    _, token = repository.enroll("Appareil")
    with repository._connect() as connection:
        connection.execute("UPDATE devices SET created_at = '2000-01-01 00:00:00'")
    assert repository.authenticate(token) is not None
    assert repository.authenticate(token, max_age_seconds=3600) is None


def test_schema_migrations_are_tracked(tmp_path):
    repository = DeviceRepository(tmp_path / "migrated.db")
    assert repository.schema_version() == 3
    again = DeviceRepository(tmp_path / "migrated.db")
    assert again.schema_version() == 3


@pytest.mark.asyncio
async def test_responses_carry_a_request_id(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 16
