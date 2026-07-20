from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.profiles import ProfileRepository
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app
from emefa.skills import build_tool_shelf


def test_repository_create_list_complete_and_buckets(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.db")
    today = date.today()
    overdue = repository.create("Relancer Horizon", due_date=(today - timedelta(days=2)).isoformat())
    due_today = repository.create("Payer la facture", due_date=today.isoformat())
    upcoming = repository.create("Préparer la réunion", due_date=(today + timedelta(days=3)).isoformat())
    dateless = repository.create("Classer les documents")

    assert overdue.bucket() == "en_retard"
    assert due_today.bucket() == "aujourdhui"
    assert upcoming.bucket() == "a_venir"
    assert dateless.bucket() == "sans_echeance"

    open_tasks = repository.list_open()
    assert [task.task_id for task in open_tasks[:3]] == [
        overdue.task_id, due_today.task_id, upcoming.task_id
    ]

    done = repository.complete(due_today.task_id)
    assert done is not None and done.status == "done" and done.completed_at
    assert repository.complete(due_today.task_id) is None
    assert len(repository.list_open()) == 3

    with pytest.raises(ValueError):
        repository.create("Date invalide", due_date="pas-une-date")


def test_task_skills_flow(tmp_path):
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "s.db"), TaskRepository(tmp_path / "s.db")
    )
    created = shelf.get("create_task").handler(
        {"title": "Relancer Horizon", "due_date": date.today().isoformat()}
    )
    task_id = created["task"]["task_id"]
    listing = shelf.get("list_tasks").handler({})
    assert listing["count"] == 1
    assert listing["tasks"][0]["bucket"] == "aujourdhui"
    completed = shelf.get("complete_task").handler({"task_id": task_id})
    assert completed["task"]["status"] == "done"
    assert shelf.get("create_task").handler({})["error"] == "title_required"
    assert shelf.get("create_task").handler({"title": "X", "due_date": "n/a"})["error"] == "invalid_due_date"
    assert shelf.get("complete_task").handler({"task_id": "absent"})["error"] == "task_not_found_or_not_open"


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


@pytest.mark.asyncio
async def test_task_created_through_conversation_and_visible_via_api(tmp_path):
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="create_task",
                    arguments={"title": "Relancer Horizon", "due_date": date.today().isoformat()},
                    call_id="call_task",
                )
            ),
            AgentStep(answer="C’est noté : je suivrai la relance d’Horizon."),
        ]
    )
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=brain,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/tasks")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = await web.post("/v1/agent/runs", json={"message": "Rappelle-moi de relancer Horizon aujourd’hui"})
        assert run.json()["status"] == "completed"
        tasks = (await web.get("/v1/tasks")).json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Relancer Horizon"
    assert tasks[0]["bucket"] == "aujourdhui"
