import smtplib

import httpx
import pytest
from pydantic import SecretStr

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.main import create_app

VOICE_HEADERS = {"Authorization": "Bearer voice-secret"}


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)
        self.histories = []

    async def think(self, history, tools):
        self.histories.append([dict(item) for item in history])
        return self.steps.pop(0)


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


def voice_app(tmp_path, brain, token: str | None = "voice-secret"):
    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "voice.db",
            cookie_secure=False,
            voice_llm_token=SecretStr(token) if token else None,
            smtp_host="smtp.test",
            smtp_from="graphistegpt@gmail.com",
        ),
        brain=brain,
    )


@pytest.mark.asyncio
async def test_auth_missing_wrong_and_unconfigured(tmp_path):
    app = voice_app(tmp_path, ScriptedBrain([]))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        payload = {"messages": [{"role": "user", "content": "Bonjour"}]}
        assert (await web.post("/v1/voice-llm/chat/completions", json=payload)).status_code == 401
        wrong = await web.post(
            "/v1/voice-llm/chat/completions", json=payload,
            headers={"Authorization": "Bearer faux"},
        )
        assert wrong.status_code == 401
    unconfigured = voice_app(tmp_path, ScriptedBrain([]), token=None)
    transport = httpx.ASGITransport(app=unconfigured)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Bonjour"}]},
        )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_voice_turn_runs_engine_and_persists(tmp_path):
    brain = ScriptedBrain([AgentStep(answer="Bonjour, je vous écoute.")])
    app = voice_app(tmp_path, brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        missing = await web.post(
            "/v1/voice-llm/chat/completions", json={"messages": []}, headers=VOICE_HEADERS
        )
        assert missing.status_code == 400
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Bonjour EMEFA"}]},
            headers=VOICE_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "Bonjour, je vous écoute."
    assert [item["content"] for item in brain.histories[0]] == ["Bonjour EMEFA"]
    assert "Derniers échanges vocaux" not in str(brain.histories[0])
    text_context = app.state.compose_text_context()
    assert "Bonjour EMEFA" in text_context and "je vous écoute" in text_context


@pytest.mark.asyncio
async def test_streamed_voice_answer_is_openai_sse(tmp_path):
    brain = ScriptedBrain([AgentStep(answer="Voici le brief du jour, rien d’urgent.")])
    app = voice_app(tmp_path, brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "Mon brief ?"}]},
            headers=VOICE_HEADERS,
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    raw = response.content.decode()
    assert '"delta"' in raw and "[DONE]" in raw
    assert "brief du jour" in raw


@pytest.mark.asyncio
async def test_voice_email_prepare_approve_send_and_announce(tmp_path):
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="email_send",
                    arguments={
                        "to": "ama@mensah.tg",
                        "subject": "Relance devis",
                        "body": "Bonjour Ama, avez-vous pu consulter le devis ?",
                    },
                    call_id="call_voice_mail",
                )
            ),
            AgentStep(answer="C’est envoyé : Ama a bien reçu la relance."),
            AgentStep(answer="Oui, l’e-mail pour Ama est parti il y a un instant."),
        ]
    )
    app = voice_app(tmp_path, brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        # 1. Spoken request prepares the e-mail but must not send it.
        prepared = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Envoie la relance à Ama"}]},
            headers=VOICE_HEADERS,
        )
        spoken = prepared.json()["choices"][0]["message"]["content"]
        assert "ama@mensah.tg" in spoken and "approbation" in spoken
        assert FakeSmtp.instances == []
        # 2. The pending approval is visible from an authenticated device.
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        pending = (await web.get("/v1/agent/approvals")).json()
        assert len(pending) == 1 and pending[0]["name"] == "email_send"
        # 3. Approval executes the send and concludes with the brain.
        decision = await web.post(
            f"/v1/agent/approvals/{pending[0]['action_id']}/decision",
            json={"approve": True},
        )
        assert decision.json()["status"] == "completed"
        assert len(FakeSmtp.instances) == 1
        assert FakeSmtp.instances[0].sent[0]["To"] == "ama@mensah.tg"
        # 4. The next voice turn knows the result and can announce it orally.
        followup = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "C’est parti ?"}]},
            headers=VOICE_HEADERS,
        )
    assert "est parti" in followup.json()["choices"][0]["message"]["content"]
    last_history = brain.histories[-1]
    tool_entries = [item for item in last_history if item.get("role") == "tool"]
    assert tool_entries and tool_entries[0]["name"] == "email_send"


@pytest.mark.asyncio
async def test_voice_rejection_never_sends(tmp_path):
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="email_send",
                    arguments={"to": "ama@mensah.tg", "subject": "S", "body": "B"},
                )
            ),
        ]
    )
    app = voice_app(tmp_path, brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Envoie le mail"}]},
            headers=VOICE_HEADERS,
        )
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        pending = (await web.get("/v1/agent/approvals")).json()
        decision = await web.post(
            f"/v1/agent/approvals/{pending[0]['action_id']}/decision",
            json={"approve": False},
        )
    assert decision.json()["status"] == "rejected"
    assert FakeSmtp.instances == []
