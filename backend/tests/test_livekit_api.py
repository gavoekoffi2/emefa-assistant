import httpx
import jwt
import pytest

from emefa.config import Settings
from emefa.infrastructure.livekit import LiveKitBroker
from emefa.main import create_app


class FakeLiveKitBroker:
    configured = True

    def __init__(self) -> None:
        self.device_ids: list[str] = []

    async def create_session(self, device_id: str) -> dict[str, str]:
        self.device_ids.append(device_id)
        return {
            "token": "short-lived-room-token",
            "url": "wss://emefa.livekit.cloud",
            "room": "emefa-private-room",
        }

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_livekit_session_requires_an_activated_private_browser(tmp_path):
    app = create_app(
        Settings(enrollment_code="LIVEKIT-PRIVATE", database_path=tmp_path / "livekit-auth.db")
    )
    app.state.livekit = FakeLiveKitBroker()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        response = await client.post("/v1/livekit/session")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_livekit_session_is_disabled_when_server_credentials_are_missing(tmp_path):
    app = create_app(
        Settings(enrollment_code="LIVEKIT-PRIVATE", database_path=tmp_path / "livekit-off.db")
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Chrome de Claude", "enrollment_code": "LIVEKIT-PRIVATE"},
        )
        assert activated.status_code == 201
        response = await client.post("/v1/livekit/session")

    assert response.status_code == 503
    assert response.json()["detail"] == "livekit_not_configured"


@pytest.mark.asyncio
async def test_livekit_session_returns_only_a_short_lived_room_ticket(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIVEKIT-PRIVATE",
            database_path=tmp_path / "livekit-ticket.db",
            livekit_url="wss://emefa.livekit.cloud",
            livekit_api_key="server-only-key",
            livekit_api_secret="server-only-secret",
        )
    )
    broker = FakeLiveKitBroker()
    app.state.livekit = broker

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Chrome de Claude", "enrollment_code": "LIVEKIT-PRIVATE"},
        )
        assert activated.status_code == 201
        response = await client.post("/v1/livekit/session")

    assert response.status_code == 200
    assert response.json() == {
        "token": "short-lived-room-token",
        "url": "wss://emefa.livekit.cloud",
        "room": "emefa-private-room",
    }
    assert broker.device_ids == [activated.json()["device_id"]]
    assert "server-only-key" not in response.text
    assert "server-only-secret" not in response.text


@pytest.mark.asyncio
async def test_livekit_broker_mints_a_bounded_private_room_with_named_agent_dispatch():
    broker = LiveKitBroker(
        url="wss://emefa.livekit.cloud",
        api_key="key-id",
        api_secret="signing-secret-signing-secret-32-bytes-minimum",
        agent_name="emefa",
        token_ttl_seconds=120,
    )

    ticket = await broker.create_session("raw-private-device-id")
    claims = jwt.decode(ticket["token"], options={"verify_signature": False})

    assert ticket["url"] == "wss://emefa.livekit.cloud"
    assert ticket["room"].startswith("emefa-")
    assert claims["video"]["room"] == ticket["room"]
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["canSubscribe"] is True
    assert "raw-private-device-id" not in claims["sub"]
    assert 115 <= claims["exp"] - claims["nbf"] <= 120
    assert claims["roomConfig"]["agents"][0]["agentName"] == "emefa"
