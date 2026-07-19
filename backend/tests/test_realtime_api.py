import httpx
import pytest

from emefa.config import Settings
from emefa.main import create_app


class FakeRealtimeGateway:
    configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_signed_url(self, safety_identifier: str) -> str:
        self.calls.append(safety_identifier)
        return "wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=test"


@pytest.mark.asyncio
async def test_realtime_session_requires_an_activated_private_browser(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "realtime.db",
            elevenlabs_api_key="test-key",
            elevenlabs_agent_id="agent_test",
        )
    )
    app.state.realtime = FakeRealtimeGateway()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_realtime_session_returns_short_lived_signed_url_without_exposing_key(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "realtime.db",
            elevenlabs_api_key="server-only-secret",
            elevenlabs_agent_id="agent_test",
        )
    )
    gateway = FakeRealtimeGateway()
    app.state.realtime = gateway
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Chrome de Claude", "enrollment_code": "VOICE-PRIVATE"},
        )
        assert activated.status_code == 201
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 200
    body = response.json()
    assert body["signed_url"].startswith("wss://api.elevenlabs.io/")
    assert "server-only-secret" not in response.text
    assert len(gateway.calls) == 1
    assert gateway.calls[0]
    assert "Chrome de Claude" not in gateway.calls[0]


@pytest.mark.asyncio
async def test_realtime_session_reports_configuration_error_when_key_is_missing(tmp_path):
    app = create_app(
        Settings(enrollment_code="VOICE-PRIVATE", database_path=tmp_path / "realtime.db")
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        await client.post(
            "/v1/web/session",
            json={"name": "Chrome", "enrollment_code": "VOICE-PRIVATE"},
        )
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 503
    assert response.json()["detail"] == "realtime_not_configured"
