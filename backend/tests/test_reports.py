"""Morning brief and evening report: deterministic, honest, customisable."""

from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.briefings import BriefingRepository
from emefa.domain.crm import CrmRepository
from emefa.domain.documents import DocumentStore
from emefa.domain.meetings import MeetingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.reports import (
    ReportPreferences,
    ReportPreferencesRepository,
    compose_evening_report,
    compose_morning_brief,
    format_evening_text,
    format_morning_text,
)
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app
from emefa.scheduler import run_evening_job

TODAY = date(2026, 7, 28)


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def ahead(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def loaded_business(tmp_path):
    database = tmp_path / "reports.db"
    profiles = ProfileRepository(database)
    profiles.update_business(
        {
            "company_name": "Horizon SARL",
            "owner_name": "Koffi Gava",
            "preferred_name": "M. Gava",
            "current_priorities": "Signer le contrat cadre",
            "goals": "Dix nouveaux clients",
        }
    )
    tasks = TaskRepository(database)
    tasks.create("Payer la facture EDF", due_date=ago(2))
    tasks.create("Préparer le comité", due_date=TODAY.isoformat())
    crm = CrmRepository(database)
    client = crm.save_contact(name="Ama Mensah", kind="client", company="Mensah Logistics")
    crm.log_interaction("Dernier échange", contact_id=client.contact_id, occurred_at=ago(60))
    crm.save_deal(
        title="Refonte du site", contact_id=client.contact_id, amount=1_500_000,
        stage="envoyé", sent_at=ago(21),
    )
    crm.save_contract(title="Cadre 2026", contact_id=client.contact_id, end_date=ahead(15), status="actif")
    crm.save_project(name="Plateforme", status="bloqué", blocker="Attente juridique")
    documents = DocumentStore(database)
    meetings = MeetingRepository(database, crm, tasks, documents)
    meetings.capture(
        title="Point projet",
        actions=[{"description": "Envoyer les specs", "owner": "Ama Mensah", "due_date": ago(3)}],
    )
    return profiles, tasks, crm, meetings, database


def test_morning_brief_reads_every_executive_signal(tmp_path):
    profiles, tasks, crm, meetings, _ = loaded_business(tmp_path)
    brief = compose_morning_brief(profiles, tasks, None, crm, meetings, today=TODAY)

    assert brief["address_as"] == "M. Gava"
    assert brief["priorities"] == "Signer le contrat cadre"
    assert [item["title"] for item in brief["tasks"]["en_retard"]] == ["Payer la facture EDF"]
    assert [item["name"] for item in brief["follow_ups"]] == ["Ama Mensah"]
    assert [item["title"] for item in brief["awaiting_deals"]] == ["Refonte du site"]
    assert [item["title"] for item in brief["expiring_contracts"]] == ["Cadre 2026"]
    assert [item["name"] for item in brief["blocked_projects"]] == ["Plateforme"]
    assert [item["owner"] for item in brief["meeting_actions"]] == ["Ama Mensah"]
    assert brief["opportunity_total"] == 1_500_000

    # Risks and recommendations are derived from those facts, never invented.
    assert any("Plateforme" in risk for risk in brief["risks"])
    assert any("Cadre 2026" in risk for risk in brief["risks"])
    assert any("en retard" in risk for risk in brief["risks"])
    assert brief["recommendations"][0] == "Traiter d'abord « Payer la facture EDF », en retard."
    assert any("Refonte du site" in item for item in brief["recommendations"])


def test_morning_text_stays_readable_and_backward_compatible():
    text = format_morning_text(
        {
            "date": "2026-07-20",
            "company_name": "Horizon SARL",
            "open_task_count": 1,
            "tasks": {"en_retard": [{"title": "Payer la facture", "due_date": "2026-07-19"}]},
            "due_follow_ups": [
                {"name": "Ama Mensah", "company": "Mensah Logistics", "next_action": "Relancer"}
            ],
            "goals": "10 nouveaux clients",
        }
    )
    assert "Brief EMEFA du 2026-07-20 — Horizon SARL" in text
    assert "[En retard] Payer la facture (échéance 2026-07-19)" in text
    assert "Ama Mensah (Mensah Logistics) — Relancer" in text
    assert "Objectifs : 10 nouveaux clients" in text
    assert "Aucune tâche ouverte." in format_morning_text({"date": "2026-07-20", "tasks": {}})


def test_sections_can_be_switched_off(tmp_path):
    profiles, tasks, crm, meetings, database = loaded_business(tmp_path)
    preferences = ReportPreferences(morning_sections=("taches", "recommandations"), evening_sections=())
    brief = compose_morning_brief(profiles, tasks, None, crm, meetings, preferences, today=TODAY)
    assert "tasks" in brief
    assert "follow_ups" not in brief
    assert "expiring_contracts" not in brief
    assert "opportunities" not in brief
    assert "recommendations" in brief

    stored = ReportPreferencesRepository(database)
    saved = stored.update(morning_sections=["relances", "inconnu"], evening_sections=["demain"])
    assert saved.morning_sections == ("relances",)  # unknown keys are dropped
    assert saved.evening_sections == ("demain",)
    assert stored.get().morning_sections == ("relances",)


def test_evening_report_summarises_the_day_and_prepares_tomorrow(tmp_path):
    profiles, tasks, crm, meetings, _ = loaded_business(tmp_path)
    done = tasks.create("Relancer le fournisseur")
    tasks.complete(done.task_id)

    report = compose_evening_report(profiles, tasks, crm, meetings, today=TODAY)
    assert report["completed_count"] == 1
    assert [item["title"] for item in report["completed"]] == ["Relancer le fournisseur"]
    assert report["remaining_count"] == 2
    assert any("Plateforme" in blocker for blocker in report["blockers"])
    assert any("en retard" in blocker for blocker in report["blockers"])
    assert any("Rattraper" in item for item in report["tomorrow"])
    assert any("Refonte du site" in item for item in report["tomorrow"])

    text = format_evening_text(report)
    assert "Rapport du soir EMEFA — 2026-07-28 — Horizon SARL" in text
    assert "Terminé aujourd'hui :" in text
    assert "Priorités de demain :" in text


class FakeEmailProvider:
    def __init__(self):
        self.sent: list[dict] = []

    def search(self, query, limit):
        return []

    def read(self, message_id):
        return {}

    def create_draft(self, to, subject, body):
        return {"status": "draft_created"}

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})
        return {"status": "sent"}


@pytest.mark.asyncio
async def test_evening_job_emails_once_under_the_standing_approval(tmp_path):
    database = tmp_path / "evening.db"
    profiles = ProfileRepository(database)
    tasks = TaskRepository(database)
    reports = BriefingRepository(database, table="evening_reports")
    provider = FakeEmailProvider()

    without = await run_evening_job(profiles, tasks, reports, provider, None)
    assert without["emailed"] is False
    assert provider.sent == []

    first = await run_evening_job(profiles, tasks, reports, provider, "dg@horizon.tg")
    assert first["emailed"] is True
    again = await run_evening_job(profiles, tasks, reports, provider, "dg@horizon.tg")
    assert again["emailed"] is True
    assert len(provider.sent) == 1
    assert "rapport du soir" in provider.sent[0]["subject"].lower()


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="Voici votre point.")


@pytest.mark.asyncio
async def test_report_endpoints_compose_live_and_store_preferences(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=Brain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    app.state.tasks.create("Signer le contrat")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/briefings/morning")).status_code == 401

        morning = await client.get("/v1/briefings/morning", headers=headers)
        assert morning.status_code == 200
        assert "Signer le contrat" in morning.json()["text"]

        evening = await client.get("/v1/briefings/evening", headers=headers)
        assert evening.status_code == 200
        assert evening.json()["content"]["kind"] == "evening"
        # The evening view is persisted so the e-mail matches what was shown.
        assert app.state.evening_reports.get(evening.json()["brief_date"]) is not None

        defaults = (await client.get("/v1/briefings/preferences", headers=headers)).json()
        assert defaults["morning_sections"] == []
        assert {item["key"] for item in defaults["available_morning"]} >= {"relances", "devis"}

        updated = await client.put(
            "/v1/briefings/preferences",
            headers=headers,
            json={"morning_sections": ["taches", "relances"], "evening_sections": ["demain"]},
        )
        assert updated.json()["morning_sections"] == ["relances", "taches"]

        narrowed = (await client.get("/v1/briefings/morning", headers=headers)).json()
        assert "opportunities" not in narrowed["content"]
