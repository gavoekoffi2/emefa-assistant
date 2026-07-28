"""Durable missions: plan, execute, verify, resume.

The point of these tests is that "completed" must mean the work happened.
Every path that could report success without it is pinned here.
"""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, AgentTool, ToolShelf
from emefa.domain.missions import (
    MAX_ATTEMPTS,
    MAX_STEPS,
    MissionOrchestrator,
    MissionRepository,
    MissionStatus,
    StepStatus,
    StepVerifier,
)
from emefa.domain.policy import ActionRisk
from emefa.main import create_app


def shelf_with(*tools: AgentTool) -> ToolShelf:
    shelf = ToolShelf()
    for tool in tools:
        shelf.add(tool)
    return shelf


def tool(name, risk=ActionRisk.LOCAL_WRITE, handler=None):
    return AgentTool(
        name=name,
        description=name,
        risk=risk,
        handler=handler or (lambda arguments: {"ok": True, **dict(arguments)}),
    )


@pytest.mark.asyncio
async def test_a_mission_runs_its_steps_in_order_and_completes(tmp_path):
    executed: list[str] = []

    def record(label):
        def handler(_arguments):
            executed.append(label)
            return {"done": label}

        return handler

    repository = MissionRepository(tmp_path / "run.db")
    orchestrator = MissionOrchestrator(
        repository, shelf_with(tool("un", handler=record("un")), tool("deux", handler=record("deux")))
    )
    mission = repository.create(
        "Préparer la proposition",
        [("Première étape", "un", {}), ("Deuxième étape", "deux", {})],
    )

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert executed == ["un", "deux"]
    assert final.status is MissionStatus.COMPLETED
    assert final.progress() == {"total": 2, "verified": 2, "failed": 0, "pending": 0}


@pytest.mark.asyncio
async def test_state_is_durable_so_a_mission_resumes_rather_than_restarts(tmp_path):
    """The whole reason missions exist. A crash between steps must not replay
    the first one — it may have sent something."""
    database = tmp_path / "resume.db"
    runs: list[str] = []
    repository = MissionRepository(database)
    orchestrator = MissionOrchestrator(
        repository,
        shelf_with(
            tool("un", handler=lambda _a: (runs.append("un"), {"ok": 1})[1]),
            tool("deux", handler=lambda _a: (runs.append("deux"), {"ok": 2})[1]),
        ),
    )
    mission = repository.create("Objectif", [("A", "un", {}), ("B", "deux", {})])

    await orchestrator.advance(mission.mission_id)
    assert runs == ["un"]

    # Everything below is a fresh process: new repository, new orchestrator,
    # same database.
    reopened = MissionRepository(database)
    resumed = MissionOrchestrator(
        reopened,
        shelf_with(
            tool("un", handler=lambda _a: (runs.append("un"), {"ok": 1})[1]),
            tool("deux", handler=lambda _a: (runs.append("deux"), {"ok": 2})[1]),
        ),
    )
    assert [item.mission_id for item in reopened.resumable()] == [mission.mission_id]

    final = await resumed.run_to_completion(mission.mission_id)
    assert runs == ["un", "deux"], "the completed step must not run twice"
    assert final.status is MissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_step_the_policy_asks_about_waits_for_the_user(tmp_path):
    repository = MissionRepository(tmp_path / "approve.db")
    sent: list[dict] = []
    orchestrator = MissionOrchestrator(
        repository,
        shelf_with(
            tool("préparer"),
            tool(
                "envoyer",
                risk=ActionRisk.COMMUNICATE,
                handler=lambda arguments: (sent.append(dict(arguments)), {"sent": True})[1],
            ),
        ),
    )
    mission = repository.create(
        "Relancer la clinique",
        [("Rédiger", "préparer", {}), ("Envoyer", "envoyer", {"to": "clinique@example.com"})],
    )

    paused = await orchestrator.run_to_completion(mission.mission_id)
    assert paused.status is MissionStatus.AWAITING_APPROVAL
    assert sent == [], "a communicate step must not run before the user says so"

    waiting = next(
        step for step in paused.steps if step.status is StepStatus.AWAITING_APPROVAL
    )
    await orchestrator.approve_step(mission.mission_id, waiting.step_id)
    final = await orchestrator.run_to_completion(mission.mission_id)

    assert sent == [{"to": "clinique@example.com"}]
    assert final.status is MissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_blocked_risk_fails_the_mission_and_approval_cannot_unblock_it(tmp_path):
    repository = MissionRepository(tmp_path / "blocked.db")
    ran: list[str] = []
    orchestrator = MissionOrchestrator(
        repository,
        shelf_with(
            tool("payer", risk=ActionRisk.MONEY, handler=lambda _a: (ran.append("x"), {})[1])
        ),
    )
    mission = repository.create("Payer", [("Payer", "payer", {})])

    final = await orchestrator.run_to_completion(mission.mission_id)
    assert final.status is MissionStatus.FAILED
    assert ran == []

    # Approval is consent to an action the policy allows, not a way around it.
    step = final.steps[0]
    await orchestrator.approve_step(mission.mission_id, step.step_id)
    assert ran == []


@pytest.mark.asyncio
async def test_a_tool_returning_an_error_is_not_a_success(tmp_path):
    """The failure CLAUDE.md 25 is about: a call that did not raise is not
    evidence the work happened."""
    repository = MissionRepository(tmp_path / "sneaky.db")
    orchestrator = MissionOrchestrator(
        repository, shelf_with(tool("écrire", handler=lambda _a: {"error": "disque plein"}))
    )
    mission = repository.create("Écrire", [("Écrire", "écrire", {})])

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert final.status is MissionStatus.FAILED
    assert final.steps[0].status is StepStatus.UNVERIFIED
    assert "disque plein" in final.steps[0].verification


@pytest.mark.asyncio
async def test_deterministic_verification_reads_the_effect_back(tmp_path):
    repository = MissionRepository(tmp_path / "verify.db")
    world: dict[str, str] = {}

    def create(arguments):
        world[arguments["id"]] = "existe"
        return {"id": arguments["id"]}

    def lying_create(arguments):
        # Claims success, changes nothing. Only a read-back catches this.
        return {"id": arguments["id"]}

    def check(_arguments, result):
        found = result.get("id") in world
        return found, "relu depuis le stockage" if found else "introuvable après coup"

    verifier = StepVerifier({"créer": check, "mentir": check})
    orchestrator = MissionOrchestrator(
        repository,
        shelf_with(tool("créer", handler=create), tool("mentir", handler=lying_create)),
        verifier,
    )

    honest = repository.create("Créer", [("Créer", "créer", {"id": "a"})])
    assert (await orchestrator.run_to_completion(honest.mission_id)).status is MissionStatus.COMPLETED

    dishonest = repository.create("Créer", [("Créer", "mentir", {"id": "b"})])
    final = await orchestrator.run_to_completion(dishonest.mission_id)
    assert final.status is MissionStatus.FAILED
    assert "introuvable" in final.steps[0].verification


@pytest.mark.asyncio
async def test_a_failing_step_is_retried_then_gives_up(tmp_path):
    repository = MissionRepository(tmp_path / "retry.db")
    attempts = {"count": 0}

    def flaky(_arguments):
        attempts["count"] += 1
        raise RuntimeError("réseau")

    orchestrator = MissionOrchestrator(repository, shelf_with(tool("fragile", handler=flaky)))
    mission = repository.create("Essayer", [("Essayer", "fragile", {})])

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert attempts["count"] == MAX_ATTEMPTS, "retrying forever burns the budget"
    assert final.status is MissionStatus.FAILED


@pytest.mark.asyncio
async def test_a_partly_successful_mission_says_so(tmp_path):
    """Distinct from failed on purpose: the user needs to know what did
    happen."""
    repository = MissionRepository(tmp_path / "partial.db")
    orchestrator = MissionOrchestrator(
        repository,
        shelf_with(
            tool("marche"),
            tool("casse", handler=lambda _a: {"error": "non"}),
        ),
    )
    mission = repository.create(
        "Deux choses", [("Une", "marche", {}), ("Deux", "casse", {})]
    )

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert final.status is MissionStatus.PARTIALLY_COMPLETED
    assert final.progress() == {"total": 2, "verified": 1, "failed": 1, "pending": 0}


@pytest.mark.asyncio
async def test_an_unknown_tool_fails_without_retrying(tmp_path):
    repository = MissionRepository(tmp_path / "unknown.db")
    orchestrator = MissionOrchestrator(repository, shelf_with(tool("connu")))
    mission = repository.create("Plan bancal", [("Étape", "inexistant", {})])

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert final.status is MissionStatus.FAILED
    assert "outil inconnu" in final.steps[0].error


def test_an_over_long_plan_is_truncated_not_refused(tmp_path):
    repository = MissionRepository(tmp_path / "long.db")
    mission = repository.create(
        "Trop d'étapes", [(f"Étape {index}", "outil", {}) for index in range(30)]
    )
    assert len(mission.steps) == MAX_STEPS


@pytest.mark.asyncio
async def test_cancel_stops_a_mission(tmp_path):
    repository = MissionRepository(tmp_path / "cancel.db")
    ran: list[str] = []
    orchestrator = MissionOrchestrator(
        repository, shelf_with(tool("faire", handler=lambda _a: (ran.append("x"), {"ok": 1})[1]))
    )
    mission = repository.create("Objectif", [("Faire", "faire", {})])
    orchestrator.cancel(mission.mission_id)

    await orchestrator.run_to_completion(mission.mission_id)

    assert ran == []
    assert repository.get(mission.mission_id).status is MissionStatus.CANCELLED


@pytest.mark.asyncio
async def test_mission_api(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/missions")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        # A plan naming a tool EMEFA does not have is refused at creation,
        # not discovered halfway through execution.
        rejected = await web.post(
            "/v1/missions",
            json={
                "goal": "Faire l'impossible",
                "steps": [{"description": "X", "tool": "téléportation", "arguments": {}}],
            },
        )
        assert rejected.status_code == 422
        assert "téléportation" in rejected.json()["detail"]

        created = await web.post(
            "/v1/missions",
            json={
                "goal": "Créer une tâche de suivi",
                "steps": [
                    {
                        "description": "Créer la tâche",
                        "tool": "create_task",
                        "arguments": {"title": "Rappeler la clinique"},
                    }
                ],
            },
        )
        assert created.status_code == 201
        mission_id = created.json()["mission_id"]
        # Creating a plan does not run it.
        assert created.json()["status"] == "planned"

        advanced = (await web.post(f"/v1/missions/{mission_id}/advance")).json()
        assert advanced["status"] == "completed"
        assert advanced["steps"][0]["verification"].startswith("deterministic")

        assert (await web.get(f"/v1/missions/{mission_id}")).json()["status"] == "completed"
        assert (await web.get("/v1/missions")).json()["missions"][0]["mission_id"] == mission_id
        assert (await web.post("/v1/missions/absente/advance")).status_code == 404
