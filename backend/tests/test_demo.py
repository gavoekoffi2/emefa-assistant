import httpx
import pytest
from pydantic import SecretStr

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.prospects import ProspectRepository
from emefa.main import create_app


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


def demo_app(tmp_path, brain, **extra):
    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "demo.db",
            cookie_secure=False,
            **extra,
        ),
        brain=brain,
    )


@pytest.mark.asyncio
async def test_scenarios_catalog_is_honest_about_availability(tmp_path):
    app = demo_app(tmp_path, ScriptedBrain([]))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/demo/scenarios")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        scenarios = (await web.get("/v1/demo/scenarios")).json()
    by_id = {s["id"]: s for s in scenarios}
    assert by_id["executive_brief"]["status"] == "live"
    # Document generation IS available (governed Word documents on main).
    assert by_id["document"]["status"] == "live"
    # Prospect discovery does not exist and must never be labelled live.
    assert by_id["business_development"]["status"] == "preview"
    assert "n'est pas disponible" in by_id["business_development"]["note"]
    # No mailbox connected in tests -> the autonomy scenario says so.
    assert "Connectez la boîte mail" in by_id["recurring_autonomy"]["note"]


def test_context_carries_anti_fake_completion_guard(tmp_path):
    app = demo_app(tmp_path, ScriptedBrain([]))
    context = app.state.compose_context()
    assert "n'annonce jamais avoir effectué une action" in context
    assert "découverte automatique de prospects" in context
    assert "raisonnement interne" in context
    # The injection-framing guard is still the opening line.
    assert context.startswith("Les informations de profil et de mémoire")


@pytest.mark.asyncio
async def test_executive_brief_scenario_runs_through_real_engine(tmp_path):
    # Scenario 1 end-to-end: the prompt drives the real get_daily_brief skill.
    ProspectRepository(tmp_path / "demo.db")  # ensure DB/migrations exist
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(name="get_daily_brief", arguments={}, call_id="c1")
            ),
            AgentStep(answer="Voici ce qui mérite votre attention : aucune tâche en retard."),
        ]
    )
    app = demo_app(tmp_path, brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = await web.post(
            "/v1/agent/runs",
            json={"message": "Qu'est-ce qui mérite mon attention aujourd'hui ?"},
        )
    body = run.json()
    assert body["status"] == "completed"
    assert body["turns"] == 2
    assert "attention" in body["answer"]
