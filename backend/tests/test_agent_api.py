import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.main import create_app


class GreetingBrain:
    async def think(self, history, tools):
        return AgentStep(answer="Bonjour Claude, EMEFA est prête.")


@pytest.mark.asyncio
async def test_agent_run_requires_device_and_returns_structured_reply(tmp_path):
    app = create_app(
        Settings(enrollment_code="ONE-TIME", database_path=tmp_path / "agent.db"),
        brain=GreetingBrain(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.post("/v1/agent/runs", json={"message": "Bonjour"})
        assert unauthorized.status_code == 401

        enrollment = await client.post(
            "/v1/devices/enroll",
            json={"name": "Claude", "enrollment_code": "ONE-TIME"},
        )
        token = enrollment.json()["token"]
        response = await client.post(
            "/v1/agent/runs",
            json={"message": "Bonjour"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "turns": 1,
        "answer": "Bonjour Claude, EMEFA est prête.",
        "pending_action": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_agent_message_cannot_be_blank(tmp_path):
    app = create_app(
        Settings(enrollment_code="ONE-TIME", database_path=tmp_path / "blank.db"),
        brain=GreetingBrain(),
    )
    token = app.state.devices.enroll("Claude")[1]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/agent/runs",
            json={"message": ""},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
