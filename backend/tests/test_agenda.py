"""The agenda opens the day, catches clashes, and briefs before a meeting."""

from datetime import date, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agenda import AgendaError, AgendaRepository, parse_moment
from emefa.domain.agent import AgentStep
from emefa.domain.crm import CrmRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.reports import (
    compose_evening_report,
    compose_morning_brief,
    format_evening_text,
    format_morning_text,
)
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app

TODAY = date(2026, 7, 28)


def at(day: date, time: str) -> str:
    return f"{day.isoformat()}T{time}"


def build(tmp_path):
    database = tmp_path / "agenda.db"
    crm = CrmRepository(database)
    tasks = TaskRepository(database)
    return crm, tasks, AgendaRepository(database, crm, tasks)


def test_moment_parsing_accepts_what_a_conversation_produces():
    assert parse_moment("2026-07-30T10:00") == "2026-07-30T10:00"
    assert parse_moment("2026-07-30 10:00") == "2026-07-30T10:00"
    assert parse_moment("2026-07-30 10:00:00") == "2026-07-30T10:00"
    assert parse_moment("2026-07-30") == "2026-07-30T00:00"
    for rejected in ("jeudi prochain", "30/07/2026", "", "2026-13-01T10:00"):
        with pytest.raises(AgendaError):
            parse_moment(rejected)


def test_day_view_is_ordered_and_labelled(tmp_path):
    _, _, agenda = build(tmp_path)
    agenda.save_event(title="Point équipe", starts_at=at(TODAY, "14:00"))
    agenda.save_event(title="Café Ama", starts_at=at(TODAY, "09:30"), location="Bureau")
    agenda.save_event(title="Demain", starts_at=at(TODAY + timedelta(days=1), "09:00"))

    digest = agenda.digest(TODAY)
    assert digest["event_count"] == 2
    assert [item["label"] for item in digest["events"]] == [
        "09:30 Café Ama — Bureau", "14:00 Point équipe"
    ]
    assert digest["first_event"] == "09:30 Café Ama — Bureau"
    assert digest["tomorrow_count"] == 1
    assert digest["tomorrow_first"] == "09:00 Demain"


def test_overlapping_appointments_are_caught(tmp_path):
    _, _, agenda = build(tmp_path)
    agenda.save_event(title="Comité", starts_at=at(TODAY, "10:00"), ends_at=at(TODAY, "11:30"))
    agenda.save_event(title="Client", starts_at=at(TODAY, "11:00"), ends_at=at(TODAY, "12:00"))
    # Back-to-back is not a clash.
    agenda.save_event(title="Déjeuner", starts_at=at(TODAY, "12:00"), ends_at=at(TODAY, "13:00"))

    conflicts = agenda.conflicts(TODAY)
    assert len(conflicts) == 1
    assert {conflicts[0]["first"]["title"], conflicts[0]["second"]["title"]} == {"Comité", "Client"}


def test_invalid_input_is_refused_rather_than_guessed(tmp_path):
    _, _, agenda = build(tmp_path)
    with pytest.raises(AgendaError):
        agenda.save_event(title="Sans date")
    with pytest.raises(AgendaError):
        agenda.save_event(title="Mauvais type", starts_at=at(TODAY, "09:00"), kind="fête")
    with pytest.raises(AgendaError):
        agenda.save_event(
            title="À l'envers", starts_at=at(TODAY, "11:00"), ends_at=at(TODAY, "10:00")
        )
    with pytest.raises(AgendaError):
        agenda.save_event(title="Client fantôme", starts_at=at(TODAY, "09:00"),
                          contact_id="Personne Inconnue")


def test_preparation_gathers_the_whole_relationship(tmp_path):
    crm, tasks, agenda = build(tmp_path)
    client = crm.save_contact(name="Ama Mensah", kind="client", company="Mensah Logistics")
    crm.save_project(
        name="Refonte digitale", contact_id=client.contact_id, status="bloqué",
        blocker="Validation des maquettes", next_step="Relancer le comité", due_date="2026-09-01",
    )
    crm.save_deal(title="Phase 1", contact_id=client.contact_id, amount=900_000,
                  stage="envoyé", sent_at="2026-07-01")
    crm.save_contract(title="Cadre 2026", contact_id=client.contact_id,
                      end_date="2026-12-31", status="actif")
    crm.log_interaction("Comité de pilotage", kind="réunion",
                        contact_id=client.contact_id, occurred_at="2026-07-20")
    tasks.create("Envoyer le planning à Ama Mensah")

    event = agenda.save_event(
        title="Réunion Refonte", starts_at=at(TODAY, "10:00"),
        contact_id="Ama Mensah", project_id="Refonte digitale",
    )
    prepared = agenda.prepare(event.event_id)

    assert prepared["context_available"] is True
    assert prepared["contact"]["name"] == "Ama Mensah"
    assert prepared["project"]["name"] == "Refonte digitale"
    assert [deal["title"] for deal in prepared["deals"]] == ["Phase 1"]
    assert prepared["history"][0]["summary"] == "Comité de pilotage"
    assert prepared["open_tasks"] == ["Envoyer le planning à Ama Mensah"]

    points = " ".join(prepared["talking_points"])
    assert "Validation des maquettes" in points
    assert "Relancer le comité" in points
    assert "Phase 1" in points
    assert "Cadre 2026" in points
    assert "2026-07-20" in points


def test_preparation_says_so_when_nothing_is_linked(tmp_path):
    _, _, agenda = build(tmp_path)
    event = agenda.save_event(title="Déjeuner personnel", starts_at=at(TODAY, "12:00"))
    prepared = agenda.prepare(event.event_id)
    assert prepared["context_available"] is False
    # No invented context — an explicit, actionable statement instead.
    assert "Aucun dossier lié" in prepared["talking_points"][0]
    with pytest.raises(AgendaError):
        agenda.prepare("inexistant")


class FakeCalendar:
    """Stands in for a future Google/Microsoft adapter."""

    source_name = "fake"

    def __init__(self, events):
        self.events = events

    def fetch(self, since, until):
        return self.events


def test_external_sync_is_idempotent_and_skips_unusable_rows(tmp_path):
    _, _, agenda = build(tmp_path)
    provider = FakeCalendar([
        {"external_id": "evt-1", "title": "Comité", "starts_at": at(TODAY, "10:00")},
        {"external_id": "evt-2", "title": "Sans heure", "starts_at": "jeudi"},
        {"title": "Sans identifiant", "starts_at": at(TODAY, "15:00")},
    ])
    first = agenda.sync(provider, TODAY, TODAY)
    assert first == {"imported": 1, "updated": 0, "skipped": 2}

    provider.events[0]["title"] = "Comité (déplacé)"
    second = agenda.sync(provider, TODAY, TODAY)
    assert second == {"imported": 0, "updated": 1, "skipped": 2}
    # Re-running never duplicates the same external event.
    assert [event.title for event in agenda.day(TODAY)] == ["Comité (déplacé)"]


def test_reports_open_on_the_schedule(tmp_path):
    crm, tasks, agenda = build(tmp_path)
    profiles = ProfileRepository(tmp_path / "agenda.db")
    profiles.update_business({"company_name": "Horizon SARL"})
    agenda.save_event(title="Comité", starts_at=at(TODAY, "10:00"), ends_at=at(TODAY, "11:30"))
    agenda.save_event(title="Client", starts_at=at(TODAY, "11:00"), ends_at=at(TODAY, "12:00"))
    agenda.save_event(title="Revue", starts_at=at(TODAY + timedelta(days=1), "08:30"))

    brief = compose_morning_brief(profiles, tasks, None, crm, None, today=TODAY, agenda=agenda)
    assert brief["agenda"]["event_count"] == 2
    assert any("Chevauchement" in risk for risk in brief["risks"])
    assert brief["recommendations"][0] == "Premier rendez-vous : 10:00 Comité."

    text = format_morning_text(brief)
    assert "Agenda du jour : 2 rendez-vous" in text
    assert "- 10:00 Comité" in text
    assert "⚠ chevauchement" in text

    report = compose_evening_report(profiles, tasks, crm, None, today=TODAY, agenda=agenda)
    assert [item["label"] for item in report["tomorrow_agenda"]] == ["08:30 Revue"]
    assert report["tomorrow"][0] == "Rendez-vous : 08:30 Revue"
    assert "Agenda de demain :" in format_evening_text(report)


class Brain:
    async def think(self, history, tools):
        return AgentStep(answer="Noté.")


@pytest.mark.asyncio
async def test_agenda_api_roundtrip_and_preparation(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=Brain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    app.state.crm.save_contact(name="Ama Mensah", kind="client")
    today = date.today()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/agenda")).status_code == 401

        created = await client.post(
            "/v1/agenda",
            headers=headers,
            json={"title": "Réunion Ama", "starts_at": at(today, "10:00"),
                  "kind": "réunion", "contact_id": "Ama Mensah", "location": "Bureau"},
        )
        assert created.status_code == 201
        event_id = created.json()["event_id"]
        assert created.json()["label"] == "10:00 Réunion Ama — Bureau"

        rejected = await client.post(
            "/v1/agenda", headers=headers,
            json={"title": "Flou", "starts_at": "un jour prochain"},
        )
        assert rejected.status_code == 422

        view = (await client.get("/v1/agenda", headers=headers)).json()
        assert view["event_count"] == 1
        assert len(view["upcoming"]) == 1

        prepared = (await client.get(f"/v1/agenda/{event_id}/preparation", headers=headers)).json()
        assert prepared["contact"]["name"] == "Ama Mensah"

        moved = await client.patch(
            f"/v1/agenda/{event_id}", headers=headers, json={"starts_at": at(today, "16:00")}
        )
        assert moved.json()["label"].startswith("16:00")

        brief = (await client.get("/v1/briefings/morning", headers=headers)).json()
        assert "16:00 Réunion Ama" in brief["text"]

        assert (await client.delete(f"/v1/agenda/{event_id}", headers=headers)).status_code == 204
        assert (await client.delete(f"/v1/agenda/{event_id}", headers=headers)).status_code == 404
