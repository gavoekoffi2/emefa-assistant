import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.profiles import ProfileRepository
from emefa.main import create_app
from emefa.skills import build_tool_shelf


class FakeEmailProvider:
    def __init__(self):
        self.sent = []
        self.drafts = []

    def search(self, query: str, limit: int):
        return [{"id": "49", "from": "client@example.com", "subject": "Devis", "date": "2026-07-20"}]

    def read(self, message_id: str):
        return {"id": message_id, "content": "Bonjour, je souhaite un devis."}

    def create_draft(self, to: str, subject: str, body: str):
        self.drafts.append((to, subject, body))
        return {"status": "draft_created"}

    def send(self, to: str, subject: str, body: str):
        self.sent.append((to, subject, body))
        return {"status": "sent"}


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


def test_email_skills_expose_provider_capabilities(tmp_path):
    provider = FakeEmailProvider()
    shelf = build_tool_shelf(ProfileRepository(tmp_path / "email.db"), email_provider=provider)

    assert shelf.get("email_search").handler({"query": "devis", "limit": 5})["messages"][0]["id"] == "49"
    assert shelf.get("email_read").handler({"message_id": "49"})["content"].startswith("Bonjour")
    assert shelf.get("email_create_draft").handler({"to": "client@example.com", "subject": "Re: Devis", "body": "Merci."})["status"] == "draft_created"
    assert provider.drafts == [("client@example.com", "Re: Devis", "Merci.")]

    described = {tool["name"]: tool for tool in shelf.describe()}
    assert described["email_search"]["risk"] == "personal_read"
    assert described["email_create_draft"]["risk"] == "local_write"
    assert described["email_send"]["risk"] == "communicate"


@pytest.mark.asyncio
async def test_email_send_requires_approval_then_executes(tmp_path):
    provider = FakeEmailProvider()
    brain = ScriptedBrain([
        AgentStep(action=RequestedAction(name="email_send", arguments={"to": "client@example.com", "subject": "Devis", "body": "Voici le devis."}, call_id="send_1")),
        AgentStep(answer="Le message a été envoyé."),
    ])
    app = create_app(Settings(enrollment_code="CODE", database_path=tmp_path / "approval.db", cookie_secure=False), brain=brain, email_provider=provider)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as web:
        await web.post("/v1/web/session", json={"name": "Test", "enrollment_code": "CODE"})
        run = await web.post("/v1/agent/runs", json={"message": "Envoie le devis"})
        assert run.json()["status"] == "confirmation_required"
        assert provider.sent == []
        action_id = run.json()["action_id"]
        approved = await web.post(f"/v1/agent/approvals/{action_id}/decision", json={"approve": True})
    assert approved.json()["status"] == "completed"
    assert provider.sent == [("client@example.com", "Devis", "Voici le devis.")]
