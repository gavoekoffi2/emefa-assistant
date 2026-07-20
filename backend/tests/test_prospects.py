from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.profiles import ProfileRepository
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app
from emefa.skills import build_tool_shelf


def test_repository_add_update_and_due_follow_ups(tmp_path):
    repository = ProspectRepository(tmp_path / "pipe.db")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    overdue = repository.add(
        "Ama Mensah", company="Mensah Logistics", email="ama@mensah.tg",
        next_action="Relancer après devis", next_action_date=yesterday,
    )
    later = repository.add(
        "Kossi Adjo", next_action_date=(date.today() + timedelta(days=5)).isoformat()
    )
    assert overdue.follow_up_due() is True
    assert later.follow_up_due() is False
    assert [p.prospect_id for p in repository.due_follow_ups()] == [overdue.prospect_id]

    won = repository.update(overdue.prospect_id, stage="gagné", notes="Contrat signé")
    assert won.stage == "gagné"
    assert won.notes == "Contrat signé"
    # A won prospect leaves the open pipeline and its follow-up is no longer due.
    assert [p.prospect_id for p in repository.list_open()] == [later.prospect_id]
    assert repository.due_follow_ups() == []
    assert repository.update("absent", stage="perdu") is None
    with pytest.raises(ValueError):
        repository.add("X", next_action_date="pas-une-date")


def test_prospect_skills_flow(tmp_path):
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "s.db"),
        prospects=ProspectRepository(tmp_path / "s.db"),
    )
    created = shelf.get("add_prospect").handler(
        {"name": "Ama Mensah", "company": "Mensah Logistics"}
    )
    prospect_id = created["prospect"]["prospect_id"]
    assert shelf.get("add_prospect").handler({})["error"] == "name_required"

    listing = shelf.get("list_pipeline").handler({})
    assert listing["count"] == 1
    assert listing["prospects"][0]["stage"] == "nouveau"

    updated = shelf.get("update_prospect").handler(
        {"prospect_id": prospect_id, "stage": "contacté", "next_action": "Appel jeudi"}
    )
    assert updated["prospect"]["stage"] == "contacté"
    bad_stage = shelf.get("update_prospect").handler(
        {"prospect_id": prospect_id, "stage": "inconnu"}
    )
    assert bad_stage["error"] == "invalid_stage"
    assert (
        shelf.get("update_prospect").handler({"prospect_id": "absent", "stage": "perdu"})["error"]
        == "prospect_not_found"
    )


def test_daily_brief_includes_due_follow_ups(tmp_path):
    prospects = ProspectRepository(tmp_path / "brief.db")
    prospects.add(
        "Ama Mensah", company="Mensah Logistics",
        next_action="Relancer", next_action_date=date.today().isoformat(),
    )
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "brief.db"),
        TaskRepository(tmp_path / "brief.db"),
        prospects=prospects,
    )
    brief = shelf.get("get_daily_brief").handler({})
    assert len(brief["due_follow_ups"]) == 1
    assert brief["due_follow_ups"][0]["name"] == "Ama Mensah"
    assert brief["due_follow_ups"][0]["next_action"] == "Relancer"


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


@pytest.mark.asyncio
async def test_prospect_created_through_conversation_and_listed_via_api(tmp_path):
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="add_prospect",
                    arguments={
                        "name": "Ama Mensah",
                        "company": "Mensah Logistics",
                        "next_action": "Envoyer le devis",
                        "next_action_date": date.today().isoformat(),
                    },
                    call_id="call_p",
                )
            ),
            AgentStep(answer="Ama Mensah est ajoutée au pipeline."),
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
        assert (await web.get("/v1/prospects")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = await web.post(
            "/v1/agent/runs",
            json={"message": "Ajoute Ama Mensah de Mensah Logistics au pipeline"},
        )
        assert run.json()["status"] == "completed"
        pipeline = (await web.get("/v1/prospects")).json()
    assert len(pipeline) == 1
    assert pipeline[0]["name"] == "Ama Mensah"
    assert pipeline[0]["follow_up_due"] is True
