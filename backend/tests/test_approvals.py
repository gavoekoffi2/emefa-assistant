import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.domain.agent import AgentEngine, AgentStep, RequestedAction, ToolShelf
from emefa.domain.profiles import ProfileRepository
from emefa.main import create_app


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


def destructive_flow_brain():
    return ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="reset_business_profile",
                    arguments={"fields": ["company_name"]},
                    call_id="call_reset",
                )
            ),
            AgentStep(answer="Profil effacé comme demandé."),
        ]
    )


@pytest_asyncio.fixture
async def activated(tmp_path):
    async def factory(brain):
        app = create_app(
            Settings(
                enrollment_code="CODE-SECRET",
                database_path=tmp_path / "approvals.db",
                cookie_secure=False,
            ),
            brain=brain,
        )
        transport = httpx.ASGITransport(app=app)
        web = httpx.AsyncClient(transport=transport, base_url="http://test")
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        return web

    yield factory


@pytest.mark.asyncio
async def test_destructive_skill_requires_then_honors_approval(activated, tmp_path):
    profiles = ProfileRepository(tmp_path / "approvals.db")
    profiles.update_business({"company_name": "Horizon SARL", "industry": "Transport"})

    web = await factory_run(activated, destructive_flow_brain())
    run = await web.post("/v1/agent/runs", json={"message": "Efface le nom de mon entreprise"})
    body = run.json()
    assert body["status"] == "confirmation_required"
    assert body["pending_action"]["name"] == "reset_business_profile"
    action_id = body["action_id"]
    assert action_id
    # Nothing executed yet.
    assert profiles.get_business().company_name == "Horizon SARL"

    pending = (await web.get("/v1/agent/approvals")).json()
    assert [item["action_id"] for item in pending] == [action_id]

    decision = await web.post(
        f"/v1/agent/approvals/{action_id}/decision", json={"approve": True}
    )
    approved = decision.json()
    assert approved["status"] == "completed"
    assert approved["answer"] == "Profil effacé comme demandé."
    business = profiles.get_business()
    assert business.company_name == ""
    assert business.industry == "Transport"
    assert (await web.get("/v1/agent/approvals")).json() == []
    # Already resolved: cannot be replayed.
    replay = await web.post(
        f"/v1/agent/approvals/{action_id}/decision", json={"approve": True}
    )
    assert replay.status_code == 404
    await web.aclose()


@pytest.mark.asyncio
async def test_rejected_action_is_never_executed(activated, tmp_path):
    profiles = ProfileRepository(tmp_path / "approvals.db")
    profiles.update_business({"company_name": "Horizon SARL"})

    web = await factory_run(activated, destructive_flow_brain())
    run = await web.post("/v1/agent/runs", json={"message": "Efface tout"})
    action_id = run.json()["action_id"]

    decision = await web.post(
        f"/v1/agent/approvals/{action_id}/decision", json={"approve": False}
    )
    body = decision.json()
    assert body["status"] == "rejected"
    assert profiles.get_business().company_name == "Horizon SARL"
    assert (await web.get("/v1/agent/approvals")).json() == []
    await web.aclose()


@pytest.mark.asyncio
async def test_unknown_or_foreign_action_is_not_found(activated):
    web = await factory_run(activated, ScriptedBrain([AgentStep(answer="Bonjour.")]))
    response = await web.post(
        "/v1/agent/approvals/inexistant/decision", json={"approve": True}
    )
    assert response.status_code == 404
    await web.aclose()


@pytest.mark.asyncio
async def test_execute_approved_rejects_unknown_tool():
    engine = AgentEngine(ScriptedBrain([]), ToolShelf())
    reply = await engine.execute_approved(RequestedAction(name="absent"))
    assert reply.status == "failed"
    assert reply.error == "unknown_tool"


async def factory_run(activated, brain):
    return await activated(brain)
