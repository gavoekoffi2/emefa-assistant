import hashlib

import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.main import create_app


@pytest_asyncio.fixture
async def client(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CLAUDE-ONLY",
            database_path=tmp_path / "emefa-test.db",
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest.mark.asyncio
async def test_enrollment_is_disabled_without_server_code(tmp_path):
    app = create_app(Settings(enrollment_code=None, database_path=tmp_path / "disabled.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/devices/enroll",
            json={"name": "Claude", "enrollment_code": "anything"},
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_device_limit_blocks_additional_enrollment(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIMITED",
            database_path=tmp_path / "limited.db",
            max_devices=1,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/devices/enroll",
            json={"name": "Premier", "enrollment_code": "LIMITED"},
        )
        second = await client.post(
            "/v1/devices/enroll",
            json={"name": "Second", "enrollment_code": "LIMITED"},
        )

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_wrong_enrollment_code_is_rejected(client):
    response = await client.post(
        "/v1/devices/enroll",
        json={"name": "Téléphone de Claude", "enrollment_code": "WRONG"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_enrolled_device_authenticates_and_plain_token_is_not_stored(client):
    enrolled = await client.post(
        "/v1/devices/enroll",
        json={"name": "Téléphone de Claude", "enrollment_code": "CLAUDE-ONLY"},
    )
    assert enrolled.status_code == 201
    payload = enrolled.json()
    assert payload["device_id"]
    assert len(payload["token"]) >= 40

    repository = client._transport.app.state.devices
    record = repository.find_by_id(payload["device_id"])
    assert record.token_hash == hashlib.sha256(payload["token"].encode()).hexdigest()
    assert payload["token"] not in repr(record)

    me = await client.get(
        "/v1/devices/me",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )
    assert me.status_code == 200
    assert me.json() == {
        "device_id": payload["device_id"],
        "name": "Téléphone de Claude",
    }


@pytest.mark.asyncio
async def test_device_can_revoke_its_own_token(client):
    enrolled = await client.post(
        "/v1/devices/enroll",
        json={"name": "À révoquer", "enrollment_code": "CLAUDE-ONLY"},
    )
    token = enrolled.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    revoked = await client.delete("/v1/devices/me", headers=headers)
    after = await client.get("/v1/devices/me", headers=headers)

    assert revoked.status_code == 204
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_invalid_device_token_returns_401(client):
    response = await client.get(
        "/v1/devices/me",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
