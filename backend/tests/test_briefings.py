import smtplib
from datetime import date, datetime, timedelta

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.briefings import BriefingRepository
from emefa.domain.profiles import ProfileRepository
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository
from emefa.infrastructure.email import SmtpEmailSender
from emefa.main import create_app
from emefa.scheduler import run_brief_job, seconds_until_hour
from emefa.skills import format_brief_text


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.sent = []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, context=None):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        self.sent.append(message)
        return {}


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    yield FakeSmtp


def test_seconds_until_hour():
    now = datetime(2026, 7, 20, 6, 30)
    assert seconds_until_hour(7, now) == 1800
    assert seconds_until_hour(6, now) == 23.5 * 3600  # next day


def test_repository_upsert_and_mark_emailed(tmp_path):
    repository = BriefingRepository(tmp_path / "b.db")
    today = date.today().isoformat()
    first = repository.save(today, {"open_task_count": 1})
    assert first.emailed is False
    repository.save(today, {"open_task_count": 2})
    assert repository.get(today).content == {"open_task_count": 2}
    repository.mark_emailed(today)
    assert repository.get(today).emailed is True


def test_format_brief_text_renders_french_summary():
    text = format_brief_text(
        {
            "date": "2026-07-20",
            "company_name": "Horizon SARL",
            "open_task_count": 1,
            "tasks": {"en_retard": [{"title": "Payer la facture", "due_date": "2026-07-19"}]},
            "due_follow_ups": [{"name": "Ama Mensah", "company": "Mensah Logistics", "next_action": "Relancer"}],
            "goals": "10 nouveaux clients",
        }
    )
    assert "Brief EMEFA du 2026-07-20 — Horizon SARL" in text
    assert "[En retard] Payer la facture (échéance 2026-07-19)" in text
    assert "Ama Mensah (Mensah Logistics) — Relancer" in text
    assert "Objectifs : 10 nouveaux clients" in text


def make_repositories(tmp_path):
    db = tmp_path / "job.db"
    profiles = ProfileRepository(db)
    profiles.update_business({"company_name": "Horizon SARL", "goals": "Grandir"})
    tasks = TaskRepository(db)
    tasks.create("Relancer Horizon", due_date=(date.today() - timedelta(days=1)).isoformat())
    return profiles, tasks, ProspectRepository(db), BriefingRepository(db)


@pytest.mark.asyncio
async def test_job_generates_once_and_emails_only_with_standing_approval(tmp_path):
    profiles, tasks, prospects, briefings = make_repositories(tmp_path)
    # Without the standing approval: stored but never e-mailed.
    result = await run_brief_job(profiles, tasks, prospects, briefings)
    assert result["emailed"] is False
    assert briefings.get(date.today().isoformat()) is not None
    assert FakeSmtp.instances == []
    # With the approval: e-mailed exactly once, even across repeated runs.
    sender = SmtpEmailSender(host="smtp.test", port=587, sender="emefa@horizon.tg")
    result = await run_brief_job(
        profiles, tasks, prospects, briefings, sender, "gavoekoffi@gmail.com"
    )
    assert result["emailed"] is True
    again = await run_brief_job(
        profiles, tasks, prospects, briefings, sender, "gavoekoffi@gmail.com"
    )
    assert again["emailed"] is True
    all_sent = [m for smtp in FakeSmtp.instances for m in smtp.sent]
    assert len(all_sent) == 1
    assert all_sent[0]["To"] == "gavoekoffi@gmail.com"
    assert "Brief EMEFA" in all_sent[0]["Subject"] or "brief" in all_sent[0]["Subject"].lower()


@pytest.mark.asyncio
async def test_todays_briefing_endpoint(tmp_path):
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
        assert (await web.get("/v1/briefings/today")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        assert (await web.get("/v1/briefings/today")).status_code == 404
        BriefingRepository(tmp_path / "api.db").save(
            date.today().isoformat(), {"date": date.today().isoformat(), "open_task_count": 0, "tasks": {}}
        )
        response = await web.get("/v1/briefings/today")
    assert response.status_code == 200
    body = response.json()
    assert body["brief_date"] == date.today().isoformat()
    assert "Aucune tâche ouverte" in body["text"]
