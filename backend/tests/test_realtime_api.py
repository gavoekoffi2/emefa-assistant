import httpx
import pytest

from emefa.config import Settings
from emefa.infrastructure.realtime import RealtimeGateway
from emefa.main import create_app


class FakeRealtimeGateway:
    configured = True
    speech_configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.speech_calls: list[str] = []

    async def get_signed_url(self, safety_identifier: str) -> str:
        self.calls.append(safety_identifier)
        return "wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=test"

    async def synthesize(self, text: str) -> bytes:
        self.speech_calls.append(text)
        return b"ID3-test-audio"


@pytest.mark.asyncio
async def test_cloned_speech_uses_the_low_latency_french_tts_model():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, content=b"ID3-fast-audio")

    gateway = RealtimeGateway(
        "secret",
        "agent_test",
        "voice_test",
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await gateway.synthesize("Bonsoir Claude.") == b"ID3-fast-audio"
    finally:
        await gateway.close()

    payload = captured["payload"]
    params = captured["params"]
    assert isinstance(payload, dict)
    assert isinstance(params, dict)
    assert payload["model_id"] == "eleven_turbo_v2_5"
    assert payload["language_code"] == "fr"
    assert params["optimize_streaming_latency"] == "3"


@pytest.mark.asyncio
async def test_realtime_session_requires_an_activated_private_browser(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "realtime.db",
            elevenlabs_api_key="test-key",
            elevenlabs_agent_id="agent_test",
        )
    )
    app.state.realtime = FakeRealtimeGateway()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_realtime_session_returns_short_lived_signed_url_without_exposing_key(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "realtime.db",
            elevenlabs_api_key="server-only-secret",
            elevenlabs_agent_id="agent_test",
        )
    )
    gateway = FakeRealtimeGateway()
    app.state.realtime = gateway
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Chrome de Claude", "enrollment_code": "VOICE-PRIVATE"},
        )
        assert activated.status_code == 201
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 200
    body = response.json()
    assert body["signed_url"].startswith("wss://api.elevenlabs.io/")
    assert "server-only-secret" not in response.text
    assert len(gateway.calls) == 1
    assert gateway.calls[0]
    assert "Chrome de Claude" not in gateway.calls[0]


@pytest.mark.asyncio
async def test_realtime_session_reports_configuration_error_when_key_is_missing(tmp_path):
    app = create_app(
        Settings(enrollment_code="VOICE-PRIVATE", database_path=tmp_path / "realtime.db")
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        await client.post(
            "/v1/web/session",
            json={"name": "Chrome", "enrollment_code": "VOICE-PRIVATE"},
        )
        response = await client.get("/v1/realtime/session")

    assert response.status_code == 503
    assert response.json()["detail"] == "realtime_not_configured"


@pytest.mark.asyncio
async def test_cloned_speech_requires_an_activated_private_browser(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "speech-auth.db",
            elevenlabs_api_key="test-key",
            elevenlabs_agent_id="agent_test",
            elevenlabs_voice_id="voice_test",
        )
    )
    app.state.realtime = FakeRealtimeGateway()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        response = await client.post("/v1/realtime/speech", json={"text": "Bonsoir Claude."})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cloned_speech_returns_audio_without_exposing_provider_credentials(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "speech.db",
            elevenlabs_api_key="server-only-secret",
            elevenlabs_agent_id="agent_test",
            elevenlabs_voice_id="voice_test",
        )
    )
    gateway = FakeRealtimeGateway()
    app.state.realtime = gateway
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Chrome de Claude", "enrollment_code": "VOICE-PRIVATE"},
        )
        assert activated.status_code == 201
        response = await client.post(
            "/v1/realtime/speech",
            json={"text": " Bonsoir Claude. "},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"ID3-test-audio"
    assert gateway.speech_calls == ["Bonsoir Claude."]
    assert "server-only-secret" not in response.text


@pytest.mark.asyncio
async def test_cloned_speech_rejects_oversized_text(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="VOICE-PRIVATE",
            database_path=tmp_path / "speech-limit.db",
            elevenlabs_api_key="test-key",
            elevenlabs_agent_id="agent_test",
            elevenlabs_voice_id="voice_test",
        )
    )
    app.state.realtime = FakeRealtimeGateway()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        await client.post(
            "/v1/web/session",
            json={"name": "Chrome", "enrollment_code": "VOICE-PRIVATE"},
        )
        response = await client.post("/v1/realtime/speech", json={"text": "x" * 901})

    assert response.status_code == 422


# -- why a synthesis was refused -------------------------------------------


def _refusing_gateway(status: int, body: object) -> RealtimeGateway:
    def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, content=body or b"")

    return RealtimeGateway(
        "secret", "agent_test", "voice_test", transport=httpx.MockTransport(handler)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        # The provider names its own failures; each needs a different action.
        (400, {"detail": {"status": "voice_not_found", "message": "no such voice"}},
         "speech_voice_not_found"),
        (401, {"detail": {"status": "invalid_api_key", "message": "bad key"}},
         "speech_key_invalid"),
        (401, {"detail": {"status": "needs_authorization"}}, "speech_key_invalid"),
        (401, {"detail": {"status": "quota_exceeded", "message": "out of credits"}},
         "speech_quota_exceeded"),
        (429, {"detail": {"status": "too_many_concurrent_requests"}}, "speech_rate_limited"),
        (401, {"detail": {"status": "detected_unusual_activity"}}, "speech_account_blocked"),
        (400, {"detail": {"status": "voice_limit_reached"}}, "speech_voice_limit_reached"),
        # Unknown names still fall back to something meaningful via the status.
        (404, {"detail": {"status": "some_future_name"}}, "speech_voice_not_found"),
        (403, {"detail": {"status": "some_future_name"}}, "speech_key_not_entitled"),
        (429, {"detail": "slow down"}, "speech_rate_limited"),
        # Provider validation errors arrive as a list.
        (422, {"detail": [{"loc": ["body", "text"], "msg": "too long"}]},
         "speech_request_invalid"),
        # A body we cannot parse at all must not crash the classifier.
        (500, b"<html>gateway error</html>", "speech_provider_rejected_request"),
        (503, None, "speech_provider_rejected_request"),
    ],
)
async def test_a_refusal_is_classified_by_its_real_cause(status, body, expected):
    """The provider says why. Collapsing every failure into one code is what
    made this undiagnosable: a typo in a voice id looked like a spent quota."""
    from emefa.infrastructure.realtime import SpeechProviderError

    gateway = _refusing_gateway(status, body)
    try:
        with pytest.raises(SpeechProviderError) as raised:
            await gateway.synthesize("Bonsoir.")
    finally:
        await gateway.close()
    assert raised.value.reason == expected
    assert raised.value.status_code == status


@pytest.mark.asyncio
async def test_the_provider_message_is_logged_but_never_returned_to_the_client(caplog):
    """A provider message can quote account details, so it belongs in the
    server log and nowhere else."""
    import logging

    from emefa.domain.agent import AgentStep

    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="ok")

    secret_message = "compte pro-42 de Koffi: crédits épuisés"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"detail": {"status": "quota_exceeded", "message": secret_message}}
        )

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        app = create_app(
            Settings(
                database_path=Path(folder) / "voice.db",
                elevenlabs_api_key="secret",
                elevenlabs_agent_id="agent_test",
                elevenlabs_voice_id="voice_test",
                cookie_secure=False,
            ),
            brain=Brain(),
        )
        app.state.realtime = RealtimeGateway(
            "secret", "agent_test", "voice_test", transport=httpx.MockTransport(handler)
        )
        _, token = app.state.devices.enroll("Poste")
        transport = httpx.ASGITransport(app=app)
        with caplog.at_level(logging.WARNING, logger="emefa.voice"):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/realtime/speech",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"text": "Bonsoir."},
                )
        await app.state.realtime.close()

    # The caller learns the reason, and only the reason.
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "speech_quota_exceeded"
    assert secret_message not in response.text
    assert "secret" not in response.text

    # The operator gets the detail, in the log, with the voice that failed.
    records = [record for record in caplog.records if record.name == "emefa.voice"]
    assert records, "the real cause must be recorded somewhere"
    assert getattr(records[0], "provider_message", "") == secret_message
    assert getattr(records[0], "voice_id", "") == "voice_test"
    # The API key must never reach the log.
    assert "secret" not in records[0].getMessage()


@pytest.mark.asyncio
async def test_a_rate_limit_is_answered_as_retryable_not_as_misconfiguration():
    """The interface distinguishes "wait" from "this will keep failing"."""
    from emefa.domain.agent import AgentStep

    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="ok")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": {"status": "too_many_concurrent_requests"}})

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        app = create_app(
            Settings(
                database_path=Path(folder) / "voice.db",
                elevenlabs_api_key="secret",
                elevenlabs_agent_id="agent_test",
                elevenlabs_voice_id="voice_test",
                cookie_secure=False,
            ),
            brain=Brain(),
        )
        app.state.realtime = RealtimeGateway(
            "secret", "agent_test", "voice_test", transport=httpx.MockTransport(handler)
        )
        _, token = app.state.devices.enroll("Poste")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/realtime/speech",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": "Bonsoir."},
            )
        await app.state.realtime.close()

    assert response.status_code == 429
    assert response.json()["detail"] == "speech_rate_limited"
