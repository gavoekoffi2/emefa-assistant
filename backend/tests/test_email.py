import smtplib

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.policy import ActionRisk, Decision, decide
from emefa.domain.profiles import ProfileRepository
from emefa.infrastructure.email import SmtpEmailSender
from emefa.main import create_app
from emefa.skills import build_tool_shelf


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.starttls_called = False
        self.login_args = None
        self.sent_messages = []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, context=None):
        self.starttls_called = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_messages.append(message)
        return {}


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    yield FakeSmtp


@pytest.mark.asyncio
async def test_adapter_sends_with_starttls_and_login():
    sender = SmtpEmailSender(
        host="smtp.test", port=587, sender="emefa@horizon.tg",
        username="emefa@horizon.tg", password="secret",
    )
    result = await sender.send("client@exemple.com", "Devis", "Bonjour,\nVoici le devis.")
    assert result == {"accepted": True, "refused_recipients": []}
    smtp = FakeSmtp.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.test", 587)
    assert smtp.starttls_called is True
    assert smtp.login_args == ("emefa@horizon.tg", "secret")
    message = smtp.sent_messages[0]
    assert message["To"] == "client@exemple.com"
    assert message["From"] == "emefa@horizon.tg"
    assert message["Subject"] == "Devis"


def test_email_skill_only_registered_when_configured(tmp_path):
    profiles = ProfileRepository(tmp_path / "email.db")
    without = build_tool_shelf(profiles)
    assert without.get("send_email") is None
    with_sender = build_tool_shelf(
        profiles, email_sender=SmtpEmailSender(host="smtp.test", port=587, sender="a@b.tld")
    )
    tool = with_sender.get("send_email")
    assert tool is not None
    assert tool.risk is ActionRisk.COMMUNICATE
    assert decide(tool.risk) is Decision.ASK


@pytest.mark.asyncio
async def test_email_skill_validates_input(tmp_path):
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "val.db"),
        email_sender=SmtpEmailSender(host="smtp.test", port=587, sender="a@b.tld"),
    )
    handler = shelf.get("send_email").handler
    assert (await handler({"to": "pas-un-email", "subject": "x", "body": "y"}))["error"] == "invalid_recipient"
    assert (await handler({"to": "c@d.tld", "subject": " ", "body": "y"}))["error"] == "subject_and_body_required"


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


def email_app(tmp_path, brain):
    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "app.db",
            cookie_secure=False,
            smtp_host="smtp.test",
            smtp_from="emefa@horizon.tg",
        ),
        brain=brain,
    )


def email_flow_brain():
    return ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="send_email",
                    arguments={
                        "to": "client@exemple.com",
                        "subject": "Relance devis",
                        "body": "Bonjour, avez-vous pu consulter notre devis ?",
                    },
                    call_id="call_mail",
                )
            ),
            AgentStep(answer="L’e-mail de relance est parti."),
        ]
    )


@pytest.mark.asyncio
async def test_email_requires_approval_then_sends(tmp_path):
    app = email_app(tmp_path, email_flow_brain())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = await web.post(
            "/v1/agent/runs", json={"message": "Relance le client par e-mail"}
        )
        body = run.json()
        assert body["status"] == "confirmation_required"
        assert body["pending_action"]["name"] == "send_email"
        assert FakeSmtp.instances == []  # nothing sent before approval
        decision = await web.post(
            f"/v1/agent/approvals/{body['action_id']}/decision", json={"approve": True}
        )
    approved = decision.json()
    assert approved["status"] == "completed"
    assert approved["answer"] == "L’e-mail de relance est parti."
    assert len(FakeSmtp.instances) == 1
    assert FakeSmtp.instances[0].sent_messages[0]["To"] == "client@exemple.com"


@pytest.mark.asyncio
async def test_rejected_email_is_never_sent(tmp_path):
    app = email_app(tmp_path, email_flow_brain())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        run = await web.post("/v1/agent/runs", json={"message": "Relance le client"})
        action_id = run.json()["action_id"]
        decision = await web.post(
            f"/v1/agent/approvals/{action_id}/decision", json={"approve": False}
        )
    assert decision.json()["status"] == "rejected"
    assert FakeSmtp.instances == []
