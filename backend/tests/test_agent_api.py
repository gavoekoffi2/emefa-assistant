import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.main import create_app


class GreetingBrain:
    async def think(self, history, tools):
        return AgentStep(answer="Bonjour Claude, EMEFA est prête.")


class RecordingEmailProvider:
    def __init__(self):
        self.sent = []

    def search(self, query, limit):
        return []

    def read(self, message_id):
        return {"id": message_id, "content": ""}

    def create_draft(self, to, subject, body):
        return {"status": "draft_created", "to": to, "subject": subject}

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})
        return {"status": "sent", "to": to, "subject": subject}


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
        "action_id": None,
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


@pytest.mark.asyncio
async def test_voice_email_tool_prepares_exact_approval_without_sending(tmp_path):
    email = RecordingEmailProvider()
    app = create_app(
        Settings(enrollment_code="ONE-TIME", database_path=tmp_path / "email-action.db"),
        brain=GreetingBrain(),
        email_provider=email,
    )
    token = app.state.devices.enroll("Claude")[1]
    transport = httpx.ASGITransport(app=app)
    payload = {
        "to": "claude@example.com",
        "subject": "Merci",
        "body": "Bonjour Claude, merci pour votre confiance.",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/agent/actions/email-send",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmation_required"
    assert body["pending_action"] == {"name": "email_send", "arguments": payload}
    assert body["action_id"]
    assert email.sent == []


@pytest.mark.asyncio
async def test_approved_voice_email_sends_once_and_returns_verified_receipt(tmp_path):
    email = RecordingEmailProvider()
    app = create_app(
        Settings(enrollment_code="ONE-TIME", database_path=tmp_path / "email-send.db"),
        brain=GreetingBrain(),
        email_provider=email,
    )
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "to": "claude@example.com",
        "subject": "Merci",
        "body": "Bonjour Claude, merci pour votre confiance.",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        prepared = await client.post(
            "/v1/agent/actions/email-send", json=payload, headers=headers
        )
        action_id = prepared.json()["action_id"]
        first = await client.post(
            f"/v1/agent/approvals/{action_id}/decision",
            json={"approve": True},
            headers=headers,
        )
        duplicate = await client.post(
            f"/v1/agent/approvals/{action_id}/decision",
            json={"approve": True},
            headers=headers,
        )

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["answer"] == "L’e-mail « Merci » a bien été envoyé à claude@example.com."
    assert duplicate.status_code == 404
    assert email.sent == [payload]
