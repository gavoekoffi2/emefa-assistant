"""Turning a request into a plan.

The tests that matter here are about honesty. A planner that always produces
a plan produces a wrong one whenever the request is ambiguous, and "prépare
une réunion avec ce client" is ambiguous.
"""

from datetime import date

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, AgentTool, ToolShelf
from emefa.domain.missions import (
    CompositePlanner,
    MissionOrchestrator,
    MissionRepository,
    Plan,
    PlanStep,
    TemplatePlanner,
    extract_subject,
    resolve_date,
    validate,
)
from emefa.domain.missions.planning import PLACEHOLDER, RESERVED_TOOLS
from emefa.domain.policy import ActionRisk
from emefa.infrastructure.planner import LLMPlanner, parse_plan
from emefa.main import create_app

MONDAY = date(2026, 7, 27)


def shelf(*names: str) -> ToolShelf:
    built = ToolShelf()
    for name in names:
        built.add(
            AgentTool(
                name=name,
                description=name,
                risk=ActionRisk.LOCAL_WRITE,
                handler=lambda arguments: {"ok": True, **dict(arguments)},
            )
        )
    return built


FULL_SHELF = ("recall", "list_pipeline", "document_create", "create_task", "get_profiles")


# ── reading the request ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Prépare une proposition pour la Clinique du Lac", "Clinique du Lac"),
        ("Réunion avec Ama Kodjo demain", "Ama Kodjo"),
        ("Organise mon voyage à Accra la semaine prochaine", "Accra"),
        ("Prépare un devis pour Horizon SARL de 1 200 000 FCFA", "Horizon SARL"),
        # Anaphora and role nouns name nobody. Returning "client" here would
        # produce a document addressed to "client".
        ("Prépare une réunion avec ce client", ""),
        ("Relance le prospect vendredi", ""),
        ("Fais le point", ""),
    ],
)
def test_subject_extraction(goal, expected):
    assert extract_subject(goal) == expected


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("relance vendredi", "2026-07-31"),
        ("réunion demain", "2026-07-28"),
        ("réunion aujourd'hui", "2026-07-27"),
        ("dans 10 jours", "2026-08-06"),
        ("la semaine prochaine", "2026-08-03"),
        ("le 2026-09-15", "2026-09-15"),
        # Said on a Monday, "lundi" means the next one, not today.
        ("lundi", "2026-08-03"),
        ("quand tu veux", ""),
    ],
)
def test_date_resolution(goal, expected):
    assert resolve_date(goal, MONDAY) == expected


# ── the template strategy ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_three_recurring_intents_plan_deterministically():
    planner = CompositePlanner([TemplatePlanner(today=MONDAY)], shelf(*FULL_SHELF))

    meeting = await planner.plan("Prépare une réunion avec la Clinique du Lac mardi")
    assert meeting.strategy == "template:preparation-reunion"
    assert meeting.executable
    assert [step.tool for step in meeting.steps] == [
        "recall",
        "list_pipeline",
        "document_create",
        "create_task",
    ]
    assert meeting.steps[-1].arguments["due_date"] == "2026-07-28"
    assert "Clinique du Lac" in meeting.steps[2].arguments["title"]

    travel = await planner.plan("Organise mon voyage à Accra la semaine prochaine")
    assert travel.strategy == "template:organisation-voyage"
    assert travel.executable
    assert any("Accra" in step.arguments.get("title", "") for step in travel.steps)
    # She says what she cannot do rather than implying she booked something.
    assert any("ne réserve rien" in note for note in travel.notes)

    proposal = await planner.plan(
        "Prépare une proposition commerciale pour Atelier Kara et relance-les vendredi"
    )
    assert proposal.strategy == "template:proposition-et-relance"
    assert proposal.steps[-1].arguments["due_date"] == "2026-07-31"
    assert any("n'invente pas de chiffres" in note for note in proposal.notes)


@pytest.mark.asyncio
async def test_every_planned_step_carries_a_success_criterion():
    """Without one, a step can only be verified as "the call returned
    something", which is the failure CLAUDE.md 25 is about."""
    planner = CompositePlanner([TemplatePlanner(today=MONDAY)], shelf(*FULL_SHELF))
    plan = await planner.plan("Prépare une réunion avec Ama Kodjo demain")
    assert plan.steps
    for step in plan.steps:
        assert len(step.success_criteria) > 20
        assert "est faite" not in step.success_criteria


@pytest.mark.asyncio
async def test_an_ambiguous_request_produces_a_question_not_a_guess():
    planner = CompositePlanner([TemplatePlanner(today=MONDAY)], shelf(*FULL_SHELF))
    plan = await planner.plan("Prépare une réunion avec ce client")

    assert not plan.executable
    assert "Avec qui, ou pour qui exactement ?" in plan.missing_information
    # Nothing addressed to an unanswered placeholder was kept.
    assert not any(PLACEHOLDER.search(str(step.arguments)) for step in plan.steps)


@pytest.mark.asyncio
async def test_context_answers_the_question_without_asking_again():
    """What the user already said in conversation must not be asked for."""
    planner = CompositePlanner([TemplatePlanner(today=MONDAY)], shelf(*FULL_SHELF))
    plan = await planner.plan(
        "Prépare une réunion avec ce client", {"sujet": "Clinique du Lac"}
    )
    assert plan.executable
    assert "Clinique du Lac" in plan.steps[2].arguments["title"]


@pytest.mark.asyncio
async def test_steps_needing_absent_tools_are_dropped_with_an_explanation():
    """A deployment without documents must not get a plan that writes one."""
    planner = CompositePlanner([TemplatePlanner(today=MONDAY)], shelf("recall", "create_task"))
    plan = await planner.plan("Prépare une réunion avec Ama Kodjo demain")

    assert [step.tool for step in plan.steps] == ["recall", "create_task"]
    assert any("document_create" in note for note in plan.notes)


# ── validation ────────────────────────────────────────────────────────────


def test_validation_rejects_unknown_tools_and_placeholders():
    plan = Plan(
        goal="Objectif",
        steps=(
            PlanStep("Bonne étape", "create_task", {"title": "Faire"}, "La tâche existe."),
            PlanStep("Outil inventé", "téléportation", {}),
            PlanStep("Valeur manquante", "create_task", {"title": "Relancer {client}"}),
        ),
        strategy="test",
    )
    validated = validate(plan, shelf("create_task"))

    assert [step.tool for step in validated.steps] == ["create_task"]
    assert "De quel client s'agit-il ?" in validated.missing_information
    assert any("téléportation" in note for note in validated.notes)


def test_a_step_without_a_criterion_gets_an_honest_generic_one():
    validated = validate(
        Plan(goal="X", steps=(PlanStep("Étape", "create_task", {"title": "T"}),)),
        shelf("create_task"),
    )
    assert "vérification structurelle" in validated.steps[0].success_criteria


# ── the chain ─────────────────────────────────────────────────────────────


class StubStrategy:
    def __init__(self, name, plan=None, raises=None):
        self.name = name
        self._plan = plan
        self._raises = raises
        self.calls = 0

    async def plan(self, request, tools):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._plan


@pytest.mark.asyncio
async def test_the_first_usable_strategy_wins_and_the_rest_are_not_called():
    first = StubStrategy(
        "a", Plan(goal="X", steps=(PlanStep("Étape", "create_task", {"title": "T"}),))
    )
    second = StubStrategy("b", Plan(goal="X", steps=()))
    planner = CompositePlanner([first, second], shelf("create_task"))

    plan = await planner.plan("X")

    assert plan.steps
    assert second.calls == 0, "the model must not be paid for when a template answered"


@pytest.mark.asyncio
async def test_a_failing_strategy_falls_through_to_the_next():
    broken = StubStrategy("a", raises=RuntimeError("provider down"))
    working = StubStrategy(
        "b", Plan(goal="X", steps=(PlanStep("Étape", "create_task", {"title": "T"}),))
    )
    planner = CompositePlanner([broken, working], shelf("create_task"))

    assert (await planner.plan("X")).steps, "a dead backend must not kill planning"


@pytest.mark.asyncio
async def test_when_nothing_can_plan_she_says_so():
    planner = CompositePlanner([], shelf("create_task"))
    plan = await planner.plan("Fais quelque chose d'indéfinissable")
    assert plan.steps == ()
    assert plan.strategy == "none"
    assert "Dites-moi ce que vous attendez" in " ".join(plan.notes)


@pytest.mark.asyncio
async def test_a_plan_can_never_contain_a_planning_tool():
    """Structural, not a prompt instruction: a model handed `plan_mission`
    will reach for it, and a plan whose first step is "make a plan" is a
    loop."""
    seen: dict[str, list[str]] = {}

    class Spy:
        name = "spy"

        async def plan(self, request, tools):
            seen["tools"] = [tool["name"] for tool in tools.describe()]
            return Plan(
                goal=request.goal,
                steps=(PlanStep("Replanifier", "plan_mission", {"goal": "encore"}),),
            )

    planner = CompositePlanner([Spy()], shelf("create_task", *RESERVED_TOOLS))
    plan = await planner.plan("Boucle")

    assert not any(name in seen["tools"] for name in RESERVED_TOOLS)
    assert plan.steps == ()


# ── the model strategy ────────────────────────────────────────────────────


def test_model_output_is_parsed_defensively():
    plan = parse_plan(
        "Objectif",
        '```json\n{"steps": [{"description": "Créer la tâche", "tool": "create_task", '
        '"arguments": {"title": "T"}, "success_criteria": "La tâche existe."}], '
        '"missing_information": ["Quelle date ?"], "notes": ["Note"]}\n```',
    )
    assert plan is not None
    assert plan.steps[0].tool == "create_task"
    assert plan.missing_information == ("Quelle date ?",)

    # Unusable output returns None so the chain falls through rather than
    # storing a plan that says nothing.
    assert parse_plan("X", "pas du JSON") is None
    assert parse_plan("X", '{"steps": []}') is None
    assert parse_plan("X", '{"steps": [{"tool": "", "description": ""}]}') is None
    # A plan that is only questions is still an answer.
    assert parse_plan("X", '{"missing_information": ["Quel client ?"]}') is not None


@pytest.mark.asyncio
async def test_the_model_planner_is_told_the_real_shelf_and_validated_after():
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"steps": ['
                                '{"description": "Créer la tâche", "tool": "create_task", '
                                '"arguments": {"title": "Rappeler"}, '
                                '"success_criteria": "La tâche existe."},'
                                '{"description": "Voler", "tool": "teleport", "arguments": {}}'
                                "]}"
                            )
                        }
                    }
                ]
            },
        )

    strategy = LLMPlanner(
        api_key="k",
        model="m",
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    )
    planner = CompositePlanner([strategy], shelf("create_task"))
    plan = await planner.plan("Rappeler la clinique")
    await strategy.close()

    assert "create_task" in captured["body"]
    # A prompt is a request, not a guarantee: the invented tool is dropped.
    assert [step.tool for step in plan.steps] == ["create_task"]
    assert any("teleport" in note for note in plan.notes)


# ── end to end ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_mission_with_open_questions_refuses_to_run(tmp_path):
    repository = MissionRepository(tmp_path / "questions.db")
    ran: list[str] = []
    orchestrator = MissionOrchestrator(
        repository,
        shelf("create_task"),
    )
    orchestrator.tools.get("create_task")
    mission = repository.create(
        "Relancer",
        [PlanStep("Relancer", "create_task", {"title": "Relancer"}, "La tâche existe.")],
        missing_information=("De quel client s'agit-il ?",),
    )

    final = await orchestrator.run_to_completion(mission.mission_id)

    assert final.status.value == "planned", "acting on a guess is the one thing forbidden"
    assert ran == []
    assert final.missing_information == ("De quel client s'agit-il ?",)


@pytest.mark.asyncio
async def test_planning_api_plans_stores_and_runs(tmp_path):
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
        assert (await web.post("/v1/missions/plan", json={"goal": "X"})).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        ambiguous = (
            await web.post(
                "/v1/missions/plan", json={"goal": "Prépare une réunion avec ce client"}
            )
        ).json()
        assert ambiguous["plan"]["executable"] is False
        assert ambiguous["plan"]["missing_information"]
        # Stored, but the orchestrator will refuse it until the question is answered.
        advanced = await web.post(
            f"/v1/missions/{ambiguous['mission']['mission_id']}/advance"
        )
        assert advanced.json()["status"] == "planned"

        answered = (
            await web.post(
                "/v1/missions/plan",
                json={
                    "goal": "Prépare une réunion avec la Clinique du Lac demain",
                },
            )
        ).json()
        assert answered["plan"]["executable"] is True
        assert answered["plan"]["strategy"].startswith("template:")
        mission_id = answered["mission"]["mission_id"]
        assert answered["mission"]["status"] == "planned", "planning does not execute"

        run = (await web.post(f"/v1/missions/{mission_id}/advance")).json()
        assert run["status"] == "completed"
        assert all(step["success_criteria"] for step in run["steps"])

        # A dry run leaves nothing behind.
        preview = (
            await web.post(
                "/v1/missions/plan",
                json={"goal": "Prépare une réunion avec Ama Kodjo demain", "save": False},
            )
        ).json()
        assert preview["mission"] is None
        assert preview["plan"]["steps"]


@pytest.mark.asyncio
async def test_the_agent_can_plan_from_the_conversation(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "tools.db",
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    tools = app.state.agent.tools
    planned = await tools.get("plan_mission").handler(
        {"goal": "Prépare une réunion avec la Clinique du Lac demain"}
    )
    assert planned["planned"] is True
    assert planned["executable"] is True

    status = tools.get("mission_status").handler({"mission_id": planned["mission_id"]})
    assert status["status"] == "planned"

    finished = await tools.get("advance_mission").handler(
        {"mission_id": planned["mission_id"]}
    )
    assert finished["status"] == "completed"

    ambiguous = await tools.get("plan_mission").handler(
        {"goal": "Prépare une réunion avec ce client"}
    )
    assert ambiguous["executable"] is False
    assert ambiguous["missing_information"]
