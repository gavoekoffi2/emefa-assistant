"""OpenAI-compatible endpoint consumed by the ElevenLabs Custom LLM bridge."""

import hmac
import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.observability import audit

router = APIRouter(prefix="/v1/voice-llm", tags=["voice-llm"])


def _persist_voice_exchange(request: Request, payload: dict[str, Any], answer: str) -> None:
    """Store the latest voice exchange so text conversations can continue it."""
    answer = answer.strip()
    if not answer:
        return
    memory = request.app.state.agent.memory
    extend = getattr(memory, "extend", None)
    if not callable(extend):
        return
    entries: list[dict[str, Any]] = []
    last_user = next(
        (
            message.get("content")
            for message in reversed(payload.get("messages") or [])
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ),
        None,
    )
    if last_user and last_user.strip():
        entries.append({"role": "user", "content": last_user.strip()[:2_000], "channel": "voice"})
    entries.append({"role": "assistant", "content": answer[:2_000], "channel": "voice"})
    extend(VOICE_CONVERSATION_ID, entries)


def _collect_sse_answer(raw: bytes) -> str:
    """Reassemble the assistant text from OpenAI-style SSE delta chunks."""
    parts: list[str] = []
    for line in raw.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if isinstance(delta, str):
            parts.append(delta)
    return "".join(parts)


def _authorize(request: Request) -> None:
    token = request.app.state.settings.voice_llm_token
    if token is None or not token.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="voice_llm_not_configured",
        )
    header = request.headers.get("Authorization", "")
    provided = header.removeprefix("Bearer ").strip()
    if not provided or not hmac.compare_digest(
        provided, token.get_secret_value().strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_voice_llm_token",
        )


@router.post("/chat/completions")
async def voice_chat_completions(request: Request):
    _authorize(request)
    proxy = request.app.state.voice_llm
    if not proxy.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="voice_llm_provider_not_configured",
        )
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_json")

    upstream_payload = proxy.build_payload(payload)
    audit(
        "voice_llm_request",
        stream=bool(payload.get("stream")),
        message_count=len(upstream_payload.get("messages") or []),
    )

    if payload.get("stream"):
        upstream_request = proxy.client.build_request(
            "POST", "/chat/completions", json=upstream_payload
        )
        try:
            upstream = await proxy.client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="voice_llm_upstream_unavailable") from exc
        if upstream.status_code != 200:
            await upstream.aread()
            await upstream.aclose()
            audit("voice_llm_upstream_error", status_code=upstream.status_code)
            raise HTTPException(status_code=502, detail="voice_llm_upstream_error")

        async def relay():
            raw = b""
            try:
                async for chunk in upstream.aiter_raw():
                    raw += chunk
                    yield chunk
            finally:
                _persist_voice_exchange(request, payload, _collect_sse_answer(raw))

        return StreamingResponse(
            relay(),
            media_type="text/event-stream",
            background=BackgroundTask(upstream.aclose),
        )

    try:
        response = await proxy.client.post("/chat/completions", json=upstream_payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="voice_llm_upstream_unavailable") from exc
    if response.status_code != 200:
        audit("voice_llm_upstream_error", status_code=response.status_code)
        raise HTTPException(status_code=502, detail="voice_llm_upstream_error")
    body = response.json()
    try:
        answer = body["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        answer = ""
    _persist_voice_exchange(request, payload, answer)
    return JSONResponse(body)
