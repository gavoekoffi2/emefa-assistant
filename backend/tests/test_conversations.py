import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentEngine, AgentStep, ToolShelf
from emefa.domain.conversations import ConversationStore
from emefa.main import create_app


def test_store_roundtrip_and_trimming(tmp_path):
    store = ConversationStore(tmp_path / "conv.db")
    store.extend("c1", [{"role": "user", "content": f"tour {index}"} for index in range(15)])
    recent = store.recent("c1", limit=12)
    assert len(recent) == 12
    assert recent[0]["content"] == "tour 3"
    assert recent[-1]["content"] == "tour 14"
    assert store.recent("autre") == []
    store.forget("c1")
    assert store.recent("c1") == []


class EchoBrain:
    def __init__(self):
        self.seen_histories = []

    async def think(self, history, tools):
        self.seen_histories.append([dict(item) for item in history])
        return AgentStep(answer=f"Réponse {len(self.seen_histories)}")


@pytest.mark.asyncio
async def test_conversation_survives_engine_restart(tmp_path):
    store = ConversationStore(tmp_path / "engine.db")
    first_brain = EchoBrain()
    engine = AgentEngine(first_brain, ToolShelf(), memory=store)
    await engine.run("Bonjour", conversation_id="device-1")

    second_brain = EchoBrain()
    restarted = AgentEngine(second_brain, ToolShelf(), memory=ConversationStore(tmp_path / "engine.db"))
    await restarted.run("Tu te souviens ?", conversation_id="device-1")

    history = second_brain.seen_histories[0]
    assert [item["content"] for item in history] == ["Bonjour", "Réponse 1", "Tu te souviens ?"]


@pytest.mark.asyncio
async def test_agent_api_keeps_context_across_app_restarts(tmp_path):
    settings = Settings(
        enrollment_code="CODE-SECRET",
        database_path=tmp_path / "api.db",
        cookie_secure=False,
    )
    brain = EchoBrain()

    app = create_app(settings, brain=brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        activated = await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        cookie = activated.cookies
        await web.post("/v1/agent/runs", json={"message": "Premier message"})

    fresh_brain = EchoBrain()
    restarted_app = create_app(settings, brain=fresh_brain)
    transport = httpx.ASGITransport(app=restarted_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies=cookie
    ) as web:
        response = await web.post("/v1/agent/runs", json={"message": "Deuxième message"})
    assert response.status_code == 200
    contents = [item["content"] for item in fresh_brain.seen_histories[0]]
    assert contents == ["Premier message", "Réponse 1", "Deuxième message"]
