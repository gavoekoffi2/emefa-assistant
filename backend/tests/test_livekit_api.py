import httpx
import jwt
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.conversations import VOICE_CONVERSATION_ID
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


class FakeVoiceAgent:
    def __init__(self, reply: AgentReply) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    async def run(self, message: str, conversation_id: str) -> AgentReply:
        self.calls.append((message, conversation_id))
        return self.reply


@pytest.mark.asyncio
async def test_livekit_worker_tool_bridge_is_disabled_without_a_server_token(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIVEKIT-PRIVATE",
            database_path=tmp_path / "worker-disabled.db",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        response = await client.post(
            "/v1/livekit/tools/execute",
            headers={"Authorization": "Bearer any-token"},
            json={"message": "Prépare le rapport"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "livekit_worker_not_configured"


@pytest.mark.asyncio
async def test_livekit_worker_tool_bridge_rejects_an_invalid_server_token(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIVEKIT-PRIVATE",
            database_path=tmp_path / "worker-auth.db",
            livekit_worker_token="worker-server-secret",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        response = await client.post(
            "/v1/livekit/tools/execute",
            headers={"Authorization": "Bearer wrong"},
            json={"message": "Prépare le rapport"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_livekit_worker_token"


@pytest.mark.asyncio
async def test_livekit_worker_tool_bridge_uses_the_governed_voice_agent(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIVEKIT-PRIVATE",
            database_path=tmp_path / "worker-tool.db",
            livekit_worker_token="worker-server-secret",
        )
    )
    voice_agent = FakeVoiceAgent(AgentReply(status="completed", turns=1, answer="Rapport prêt."))
    app.state.voice_agent = voice_agent
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        response = await client.post(
            "/v1/livekit/tools/execute",
            headers={"Authorization": "Bearer worker-server-secret"},
            json={"message": " Prépare le rapport "},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "answer": "Rapport prêt.",
        "error": None,
        "action_id": None,
    }
    assert voice_agent.calls == [("Prépare le rapport", VOICE_CONVERSATION_ID)]


@pytest.mark.asyncio
async def test_livekit_worker_tool_bridge_surfaces_existing_human_approval(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="LIVEKIT-PRIVATE",
            database_path=tmp_path / "worker-approval.db",
            livekit_worker_token="worker-server-secret",
        )
    )
    voice_agent = FakeVoiceAgent(
        AgentReply(
            status="confirmation_required",
            turns=1,
            pending_action=RequestedAction(
                name="email_send",
                arguments={"to": "client@example.com", "subject": "Offre", "body": "Bonjour"},
            ),
        )
    )
    app.state.voice_agent = voice_agent
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://emefa.test"
    ) as client:
        response = await client.post(
            "/v1/livekit/tools/execute",
            headers={"Authorization": "Bearer worker-server-secret"},
            json={"message": "Envoie l'offre"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmation_required"
    assert body["action_id"]
    assert "approbation" in body["answer"].lower()
    pending = app.state.approvals.pending_for(VOICE_CONVERSATION_ID)
    assert [item.action_id for item in pending] == [body["action_id"]]
