"""A captured meeting must actually change the system, not just be stored."""

from datetime import date

import httpx
import pytest
from docx import Document

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.crm import CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.meetings import MeetingRepository
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app


def engine(tmp_path):
    database = tmp_path / "meetings.db"
    crm = CrmRepository(database)
    tasks = TaskRepository(database)
    documents = DocumentStore(database)
    return crm, tasks, documents, MeetingRepository(database, crm, tasks, documents)


def test_capture_produces_minutes_tasks_project_update_and_history(tmp_path):
    crm, tasks, documents, meetings = engine(tmp_path)
    client = crm.save_contact(name="Horizon SARL", kind="client")
    project = crm.save_project(
        name="Refonte digitale", contact_id=client.contact_id, next_step="Ancienne étape"
    )

    result = meetings.capture(
        title="Comité de pilotage",
        occurred_at="2026-07-27",
        participants=["Koffi Gava", "Ama Mensah"],
        summary="Revue de l'avancement et arbitrage du périmètre.",
        decisions=["Le périmètre reste inchangé", "Livraison décalée au 15 août"],
        actions=[
            {"description": "Envoyer le planning révisé", "owner": "moi", "due_date": "2026-07-30"},
            {"description": "Valider les maquettes", "owner": "Ama Mensah", "due_date": "2026-08-05"},
        ],
        project="Refonte digitale",
    )

    # 1 — real minutes, as an editable Word document
    assert result["document"]["kind"] == "document"
    text = "\n".join(
        p.text for p in Document(str(documents.get(result["document"]["document_id"]))).paragraphs
    )
    assert "Comité de pilotage" in text
    assert "Le périmètre reste inchangé" in text

    # 2/3 — decisions and actions with owners and deadlines
    assert result["decisions"] == ["Le périmètre reste inchangé", "Livraison décalée au 15 août"]
    assert [action["owner"] for action in result["actions"]] == ["moi", "Ama Mensah"]

    # 4 — a task only for what the executive owns
    assert len(result["tasks_created"]) == 1
    created = tasks.get(result["tasks_created"][0])
    assert created.title == "Envoyer le planning révisé"
    assert created.due_date == "2026-07-30"

    # 5 — the project moved on
    assert crm.get_project(project.project_id).next_step == "Envoyer le planning révisé"

    # 6 — the relationship remembers the meeting
    history = crm.interactions_for(contact_id=client.contact_id)
    assert history[0].kind == "réunion"
    assert result["interaction_id"] is not None

    # Someone else's action stays on the chase list
    chase = meetings.open_actions()
    assert [item["owner"] for item in chase] == ["Ama Mensah"]


def test_unknown_links_are_reported_instead_of_silently_dropped(tmp_path):
    _, _, _, meetings = engine(tmp_path)
    result = meetings.capture(title="Point rapide", project="Projet fantôme", contact="Client inconnu")
    assert result["unresolved_links"] == ["projet:Projet fantôme", "contact:Client inconnu"]
    assert result["project_id"] is None
    assert result["interaction_id"] is None


def test_capture_requires_a_title_and_survives_empty_actions(tmp_path):
    _, _, _, meetings = engine(tmp_path)
    with pytest.raises(ValueError):
        meetings.capture(title="   ")
    result = meetings.capture(title="Réunion sans suite", actions=[{"description": "  "}])
    assert result["actions"] == []
    assert result["tasks_created"] == []
    stored = meetings.get(result["meeting_id"])
    assert stored["title"] == "Réunion sans suite"
    assert meetings.delete(result["meeting_id"]) is True
    assert meetings.get(result["meeting_id"]) is None


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="Compte rendu prêt.")


@pytest.mark.asyncio
async def test_meetings_api_captures_and_lists(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=Brain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/meetings")).status_code == 401

        created = await client.post(
            "/v1/meetings",
            headers=headers,
            json={
                "title": "Revue hebdomadaire",
                "occurred_at": date.today().isoformat(),
                "participants": ["Koffi"],
                "summary": "Avancement général.",
                "decisions": ["Prioriser la refonte"],
                "actions": [{"description": "Préparer le budget", "owner": "moi"}],
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert len(body["tasks_created"]) == 1

        listing = (await client.get("/v1/meetings", headers=headers)).json()
        assert listing["meetings"][0]["title"] == "Revue hebdomadaire"
        assert listing["meetings"][0]["decision_count"] == 1

        detail = (await client.get(f"/v1/meetings/{body['meeting_id']}", headers=headers)).json()
        assert detail["decisions"] == ["Prioriser la refonte"]

        assert (await client.delete(f"/v1/meetings/{body['meeting_id']}", headers=headers)).status_code == 204
        assert (await client.get(f"/v1/meetings/{body['meeting_id']}", headers=headers)).status_code == 404
