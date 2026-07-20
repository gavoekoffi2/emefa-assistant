import json

import httpx
import pytest
from pydantic import SecretStr

from emefa.config import Settings
from emefa.domain.profiles import ProfileRepository
from emefa.infrastructure.voice_llm import VoiceLLMProxy
from emefa.main import create_app


def make_app(tmp_path, token: str | None = "voice-secret", upstream_handler=None):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "voice.db",
            cookie_secure=False,
            openrouter_api_key=SecretStr("sk-or-test"),
            voice_llm_token=SecretStr(token) if token else None,
        )
    )
    if upstream_handler is not None:
        app.state.voice_llm = VoiceLLMProxy(
            api_key="sk-or-test",
            model="deepseek/deepseek-chat",
            base_url="https://upstream.test/v1",
            context_provider=ProfileRepository(tmp_path / "voice.db").system_context,
            transport=httpx.MockTransport(upstream_handler),
        )
    return app


@pytest.mark.asyncio
async def test_requires_token_and_rejects_bad_token(tmp_path):
    app = make_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        missing = await web.post("/v1/voice-llm/chat/completions", json={"messages": []})
        assert missing.status_code == 401
        wrong = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": []},
            headers={"Authorization": "Bearer mauvais"},
        )
        assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_unconfigured_token_returns_503(tmp_path):
    app = make_app(tmp_path, token=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post("/v1/voice-llm/chat/completions", json={"messages": []})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_injects_profile_context_and_forwards(tmp_path):
    seen: list[dict] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Bonjour."}}]}
        )

    app = make_app(tmp_path, upstream_handler=upstream)
    ProfileRepository(tmp_path / "voice.db").update_business({"company_name": "Horizon SARL"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={
                "model": "ignored-model",
                "messages": [
                    {"role": "system", "content": "Persona ElevenLabs"},
                    {"role": "user", "content": "Bonjour"},
                ],
            },
            headers={"Authorization": "Bearer voice-secret"},
        )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Bonjour."
    body = seen[0]
    assert body["model"] == "deepseek/deepseek-chat"
    assert body["messages"][0]["role"] == "system"
    assert "Horizon SARL" in body["messages"][0]["content"]
    assert body["messages"][1]["content"] == "Persona ElevenLabs"
    assert body["messages"][2]["content"] == "Bonjour"


@pytest.mark.asyncio
async def test_streaming_is_passed_through_as_sse(tmp_path):
    chunks = (
        b'data: {"choices":[{"delta":{"content":"Bon"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"jour"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    async def chunk_stream():
        yield chunks

    def upstream(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            content=chunk_stream(),
            headers={"content-type": "text/event-stream"},
        )

    app = make_app(tmp_path, upstream_handler=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "Bonjour"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.content == chunks


@pytest.mark.asyncio
async def test_upstream_error_maps_to_502(tmp_path):
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limited"})

    app = make_app(tmp_path, upstream_handler=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Bonjour"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_voice_exchange_is_persisted_and_shared_with_text_context(tmp_path):
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "La réunion est confirmée pour jeudi."}}]},
        )

    app = make_app(tmp_path, upstream_handler=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Confirme la réunion de jeudi"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
    assert response.status_code == 200
    text_context = app.state.compose_text_context()
    assert "Derniers échanges vocaux" in text_context
    assert "Confirme la réunion de jeudi" in text_context
    assert "La réunion est confirmée pour jeudi." in text_context
    # The voice bridge context must NOT duplicate the recap: the provider
    # already receives the full voice history in the request messages.
    assert "Derniers échanges vocaux" not in app.state.compose_context()


@pytest.mark.asyncio
async def test_streamed_voice_answer_is_reassembled_and_persisted(tmp_path):
    async def chunk_stream():
        yield b'data: {"choices":[{"delta":{"content":"Bien "}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":"re\xc3\xa7u."}}]}\n\n'
        yield b"data: [DONE]\n\n"

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=chunk_stream(), headers={"content-type": "text/event-stream"}
        )

    app = make_app(tmp_path, upstream_handler=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"stream": True, "messages": [{"role": "user", "content": "Note bien"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
        assert response.status_code == 200
    text_context = app.state.compose_text_context()
    assert "Bien reçu." in text_context
    assert "Note bien" in text_context


@pytest.mark.asyncio
async def test_conversation_clear_also_wipes_voice_channel(tmp_path):
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "Compris."}}]})

    app = make_app(tmp_path, upstream_handler=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Souviens-toi de ça"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
        assert "Derniers échanges vocaux" in app.state.compose_text_context()
        cleared = await web.delete("/v1/agent/conversation")
        assert cleared.status_code == 204
    assert "Derniers échanges vocaux" not in app.state.compose_text_context()
