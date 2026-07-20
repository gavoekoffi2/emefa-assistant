"""OpenAI-compatible endpoint consumed by the ElevenLabs Custom LLM bridge."""

import hmac

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from emefa.observability import audit

router = APIRouter(prefix="/v1/voice-llm", tags=["voice-llm"])


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
        return StreamingResponse(
            upstream.aiter_raw(),
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
    return JSONResponse(response.json())
