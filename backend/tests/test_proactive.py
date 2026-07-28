"""Governed proactive initiatives.

The tests that matter are the restraints: a level-5 initiative always needs a
human, a persistent signal produces one card and not seven, a pass is bounded,
and nothing in the collection path can reach a tool.
"""

from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain import storage
from emefa.domain.agent import AgentStep
from emefa.domain.budget import BudgetGuard, UsageTracker
from emefa.domain.events import EventBus, InitiativeRaised
from emefa.domain.memories import MemoryRepository
from emefa.domain.policy import ActionRisk
from emefa.domain.proactive import (
    AutonomyLevel,
    Initiative,
    InitiativeRepository,
    InitiativeStatus,
    InitiativeType,
    ProactiveEngine,
    default_collectors,
    needs_human_validation,
    new_initiative_id,
)
from emefa.domain.proactive.collectors import STALE_PROSPECT_DAYS, overdue_tasks
from emefa.domain.proactive.engine import MAX_PER_PASS
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app


def make_initiative(**overrides) -> Initiative:
    fields = {
        "initiative_id": new_initiative_id(),
        "type": InitiativeType.SUGGESTION,
        "title": "Titre",
        "reason": "Parce que.",
        "next_action": "Faire la chose.",
        "dedupe_key": "clef",
    }
    return Initiative(**{**fields, **overrides})


def test_level_five_always_needs_a_human():
    """Send, publish, pay, delete. Configuration must not be able to loosen
    this — those are the acts that cannot be taken back."""
    assert needs_human_validation(
        make_initiative(
            autonomy_level=AutonomyLevel.EXTERNAL_ACTION, risk=ActionRisk.OBSERVE
        )
    )
    # Below level 5, the risk policy still governs.
    assert needs_human_validation(
        make_initiative(autonomy_level=AutonomyLevel.SUGGEST, risk=ActionRisk.COMMUNICATE)
    )
    assert not needs_human_validation(
        make_initiative(autonomy_level=AutonomyLevel.PREPARE, risk=ActionRisk.PERSONAL_READ)
    )


def test_the_same_concern_is_raised_once(tmp_path):
    repository = InitiativeRepository(tmp_path / "dedupe.db")
    first = repository.raise_initiative(make_initiative(dedupe_key="tasks:2026-07-28"))
    second = repository.raise_initiative(make_initiative(dedupe_key="tasks:2026-07-28"))

    assert first is not None
    assert second is None, "a signal that persists must not produce a second card"
    assert len(repository.open_initiatives()) == 1

    # Once closed, the same concern may legitimately return.
    repository.set_status(first.initiative_id, InitiativeStatus.DISMISSED)
    assert repository.raise_initiative(make_initiative(dedupe_key="tasks:2026-07-28")) is not None


def test_overdue_initiatives_expire_themselves(tmp_path):
    repository = InitiativeRepository(tmp_path / "expire.db")
    repository.raise_initiative(
        make_initiative(dedupe_key="hier", deadline="2020-01-01T00:00:00+00:00")
    )
    repository.raise_initiative(
        make_initiative(dedupe_key="plus-tard", deadline="2099-01-01T00:00:00+00:00")
    )

    assert repository.expire_overdue() == 1
    remaining = repository.open_initiatives()
    assert [item.dedupe_key for item in remaining] == ["plus-tard"]


def test_the_instance_ceiling_clamps_autonomy_down_never_up(tmp_path):
    repository = InitiativeRepository(tmp_path / "clamp.db")
    engine = ProactiveEngine(
        repository,
        [lambda _today: [make_initiative(autonomy_level=AutonomyLevel.EXTERNAL_ACTION)]],
        max_autonomy=AutonomyLevel.SUGGEST,
    )
    engine.run()
    assert repository.open_initiatives()[0].autonomy_level is AutonomyLevel.SUGGEST


def test_a_pass_is_bounded(tmp_path):
    repository = InitiativeRepository(tmp_path / "bounded.db")
    engine = ProactiveEngine(
        repository,
        [
            lambda _today: [
                make_initiative(dedupe_key=f"clef-{index}") for index in range(50)
            ]
        ],
    )
    report = engine.run()
    assert report.raised == MAX_PER_PASS
    assert len(repository.open_initiatives()) == MAX_PER_PASS


def test_one_broken_collector_does_not_silence_the_others(tmp_path):
    repository = InitiativeRepository(tmp_path / "broken.db")

    def explodes(_today):
        raise RuntimeError("collector bug")

    engine = ProactiveEngine(
        repository, [explodes, lambda _today: [make_initiative(dedupe_key="ok")]]
    )
    report = engine.run()

    assert report.errors == ("RuntimeError",)
    assert report.raised == 1, "a silent proactive engine is worse than a noisy one"


def test_an_exhausted_budget_stops_a_pass(tmp_path):
    database = tmp_path / "budget.db"
    repository = InitiativeRepository(database)
    tracker = UsageTracker(database)
    tracker.record("proactive", 5_000, 0)
    engine = ProactiveEngine(
        repository,
        [lambda _today: [make_initiative()]],
        budget=BudgetGuard(tracker, {"proactive": 100}),
    )
    report = engine.run()
    assert report.skipped_budget is True
    assert repository.open_initiatives() == []


def test_raising_publishes_an_event(tmp_path):
    bus = EventBus()
    seen: list[InitiativeRaised] = []
    bus.subscribe(InitiativeRaised, seen.append)
    engine = ProactiveEngine(
        InitiativeRepository(tmp_path / "bus.db"),
        [lambda _today: [make_initiative(autonomy_level=AutonomyLevel.EXTERNAL_ACTION)]],
        bus=bus,
        max_autonomy=AutonomyLevel.EXTERNAL_ACTION,
    )
    engine.run()
    assert len(seen) == 1
    assert seen[0].requires_validation is True


def test_collectors_notice_the_things_that_matter(tmp_path):
    database = tmp_path / "collect.db"
    tasks = TaskRepository(database)
    prospects = ProspectRepository(database)
    memories = MemoryRepository(database)
    today = date.today()

    tasks.create("Envoyer le devis", due_date=(today - timedelta(days=2)).isoformat())
    prospects.add(
        "Clinique du Lac",
        next_action="Relancer",
        next_action_date=(today - timedelta(days=1)).isoformat(),
    )
    stale = prospects.add("Atelier Kara")
    # `update()` always stamps updated_at with CURRENT_TIMESTAMP, so ageing a
    # row has to go through SQL. Doing it any other way would leave this
    # collector untested while the assertions looked satisfied.
    with storage.connect(database) as connection:
        connection.execute(
            "UPDATE prospects SET updated_at = ? WHERE prospect_id = ?",
            (
                (today - timedelta(days=STALE_PROSPECT_DAYS + 5)).isoformat(),
                stale.prospect_id,
            ),
        )
    memories.record_fact("utilisateur", "souhaite", "ouvrir à Accra", "goal")
    memories.record_fact("utilisateur", "souhaite", "ouvrir à Abidjan", "goal")

    engine = ProactiveEngine(
        InitiativeRepository(database),
        default_collectors(tasks, prospects, memories),
    )
    engine.run(today)

    titles = " | ".join(item.title for item in engine.initiatives.open_initiatives())
    assert "en retard" in titles
    assert "relance" in titles
    assert "sans suite" in titles
    assert "mis à jour" in titles


def test_a_follow_up_initiative_prepares_but_never_sends(tmp_path):
    """The line that keeps proactivity trustworthy: EMEFA may write the
    draft unprompted, never deliver it."""
    database = tmp_path / "prepare.db"
    prospects = ProspectRepository(database)
    prospects.add(
        "Clinique du Lac", next_action="Relancer", next_action_date=date.today().isoformat()
    )
    engine = ProactiveEngine(
        InitiativeRepository(database),
        default_collectors(TaskRepository(database), prospects, MemoryRepository(database)),
        max_autonomy=AutonomyLevel.EXTERNAL_ACTION,
    )
    engine.run()

    follow_up = next(
        item for item in engine.initiatives.open_initiatives() if "relance" in item.title
    )
    assert follow_up.autonomy_level is AutonomyLevel.PREPARE
    assert follow_up.autonomy_level < AutonomyLevel.EXTERNAL_ACTION


def test_collector_reads_are_side_effect_free(tmp_path):
    """Nothing in the collection path may reach a tool."""
    database = tmp_path / "sideeffects.db"
    tasks = TaskRepository(database)
    tasks.create("Une tâche", due_date="2020-01-01")
    before = [task.task_id for task in tasks.list_open()]

    overdue_tasks(tasks)(date.today())

    assert [task.task_id for task in tasks.list_open()] == before


@pytest.mark.asyncio
async def test_command_centre_api(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    database = tmp_path / "api.db"
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET", database_path=database, cookie_secure=False
        ),
        brain=Brain(),
    )
    TaskRepository(database).create("Devis en retard", due_date="2020-01-01")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/initiatives")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )

        assert (await web.get("/v1/initiatives")).json()["initiatives"] == []

        refreshed = (await web.post("/v1/initiatives/refresh")).json()
        assert refreshed["raised"] >= 1
        # A second pass finds the same concern and does not duplicate it.
        assert (await web.post("/v1/initiatives/refresh")).json()["raised"] == 0

        listing = (await web.get("/v1/initiatives")).json()
        initiative = listing["initiatives"][0]
        assert initiative["status"] == "pending"
        assert "autonomy_level" in initiative

        dismissed = await web.post(f"/v1/initiatives/{initiative['initiative_id']}/dismiss")
        assert dismissed.json()["status"] == "dismissed"
        assert (await web.get("/v1/initiatives")).json()["initiatives"] == []
        assert (await web.post("/v1/initiatives/absente/approve")).status_code == 404

        report = (await web.get("/v1/initiatives/curator")).json()
        assert report["pricing_configured"] is False
        # Never a monetary figure computed from a price nobody entered.
        assert "coût non calculé" in report["text"]
