"""ElevenLabs Custom-LLM endpoint for EMEFA.

Production voice uses a true streaming proxy: provider SSE bytes are relayed as
they arrive, including client-tool calls for ``emefa_execute``. The governed
engine remains the fallback for tests or deployments without a provider proxy.
"""

from __future__ import annotations

import hmac
import asyncio
import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.observability import audit, monotonic_ms

router = APIRouter(prefix="/v1/voice-llm", tags=["voice-llm"])

_ERROR_SPOKEN = {
    "brain_unavailable": "Le moteur de langage est indisponible pour le moment. Réessayons dans un instant.",
    "unknown_tool": "J’ai tenté une action que je ne connais pas. Reformulez votre demande.",
    "tool_invalid_arguments": "Les informations nécessaires à cette action sont incomplètes ou invalides. Vérifions-les puis réessayons.",
    "tool_execution_failed": "L’outil n’a pas pu terminer l’action. Rien n’a été confirmé comme exécuté. Réessayons dans un instant.",
    "turn_budget_exhausted": "Cette demande est trop complexe pour un seul échange. Découpons-la.",
    "invalid_brain_step": "Le moteur a renvoyé une réponse invalide. Réessayez.",
}


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


def _last_user_message(payload: dict[str, Any]) -> str | None:
    return next(
        (
            item.get("content")
            for item in reversed(payload.get("messages") or [])
            if isinstance(item, dict)
            and item.get("role") == "user"
            and isinstance(item.get("content"), str)
        ),
        None,
    )


def _persist_voice_exchange(request: Request, payload: dict[str, Any], answer: str) -> None:
    answer = answer.strip()
    if not answer:
        return
    memory = request.app.state.conversations
    entries: list[dict[str, Any]] = []
    last_user = _last_user_message(payload)
    if last_user and last_user.strip():
        entries.append(
            {
                "role": "user",
                "content": last_user.strip()[:2_000],
                "channel": "voice",
            }
        )
    entries.append(
        {"role": "assistant", "content": answer[:2_000], "channel": "voice"}
    )
    memory.extend(VOICE_CONVERSATION_ID, entries)
    _schedule_voice_ingestion(request, last_user or "", answer)


def _schedule_voice_ingestion(request: Request, user_text: str, answer: str) -> None:
    """Feed finalized voice turns to factual memory without delaying audio."""
    ingestor = getattr(request.app.state, "memory_ingestor", None)
    if (
        ingestor is None
        or not getattr(request.app.state, "live_extraction", False)
        or not user_text.strip()
        or not answer.strip()
    ):
        return
    transcript = f"[utilisateur, voix] {user_text.strip()}\n[EMEFA] {answer.strip()}"
    tasks: set[asyncio.Task[Any]] = request.app.state.background_tasks
    task = asyncio.create_task(ingestor.ingest(transcript, source="voice"))
    tasks.add(task)

    def finished(done: asyncio.Task[Any]) -> None:
        tasks.discard(done)
        try:
            result = done.result()
            audit("voice_memory_ingested", facts=getattr(result, "total", 0))
        except Exception as error:
            # Background memory must never surface as a streaming/response
            # failure, but failures remain observable instead of disappearing.
            audit("voice_memory_ingestion_failed", error=type(error).__name__)

    task.add_done_callback(finished)


def _collect_sse_answer(raw: bytes) -> str:
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


def _spoken_confirmation(action: RequestedAction) -> str:
    if action.name == "email_send":
        to = str(action.arguments.get("to", ""))
        subject = str(action.arguments.get("subject", ""))
        return (
            f"J’ai préparé l’e-mail pour {to}, objet « {subject} ». "
            "Par sécurité, l’envoi attend votre approbation : la carte vient "
            "d’apparaître à l’écran. Dites-moi quand c’est fait."
        )
    labels = {
        "reset_business_profile": "l’effacement du profil professionnel",
        "forget_memory": "l’oubli d’un souvenir",
    }
    label = labels.get(action.name, f"l’action {action.name}")
    return (
        f"J’ai préparé {label}. Par sécurité, approuvez-la sur l’écran "
        "pour que je l’exécute."
    )


def _spoken_reply(request: Request, reply: AgentReply) -> str:
    if reply.status == "completed" and reply.answer:
        return reply.answer
    if reply.status == "confirmation_required" and reply.pending_action is not None:
        pending = request.app.state.approvals.create(
            VOICE_CONVERSATION_ID, reply.pending_action
        )
        audit(
            "approval_created",
            channel="voice",
            action_id=pending.action_id,
            tool=pending.tool_name,
        )
        return _spoken_confirmation(reply.pending_action)
    if reply.status == "blocked":
        return "Cette action est bloquée par la politique de sécurité d’EMEFA."
    return _ERROR_SPOKEN.get(
        reply.error or "", "La demande n’a pas abouti. Réessayez."
    )


def _completion_json(text: str) -> dict[str, Any]:
    return {
        "id": "emefa-voice",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }


def _sse_stream(text: str):
    async def generate():
        words = text.split(" ")
        step = 8
        for start in range(0, len(words), step):
            piece = " ".join(words[start : start + step])
            if start + step < len(words):
                piece += " "
            data = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": piece},
                            "finish_reason": None,
                        }
                    ]
                },
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n".encode()
        yield b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"

    return generate()


async def _proxy_completion(request: Request, payload: dict[str, Any]):
    proxy = request.app.state.voice_llm
    upstream_payload = proxy.build_payload(payload)
    audit(
        "voice_llm_request",
        mode="streaming_proxy",
        stream=bool(payload.get("stream")),
        message_count=len(upstream_payload.get("messages") or []),
    )

    if payload.get("stream"):
        started = monotonic_ms()
        upstream_request = proxy.client.build_request(
            "POST", "/chat/completions", json=upstream_payload
        )
        try:
            upstream = await proxy.client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail="voice_llm_upstream_unavailable"
            ) from exc
        if upstream.status_code != 200:
            await upstream.aread()
            await upstream.aclose()
            audit("voice_llm_upstream_error", status_code=upstream.status_code)
            raise HTTPException(status_code=502, detail="voice_llm_upstream_error")

        async def relay():
            raw = bytearray()
            first_chunk_seen = False
            completed = False
            try:
                async for chunk in upstream.aiter_raw():
                    if not first_chunk_seen:
                        first_chunk_seen = True
                        audit(
                            "voice_llm_first_chunk",
                            duration_ms=round(monotonic_ms() - started, 1),
                        )
                    raw.extend(chunk)
                    yield chunk
                completed = b"data: [DONE]" in raw
            finally:
                audit(
                    "voice_llm_stream_finished",
                    completed=completed,
                    duration_ms=round(monotonic_ms() - started, 1),
                )
                if completed:
                    _persist_voice_exchange(
                        request, payload, _collect_sse_answer(bytes(raw))
                    )

        return StreamingResponse(
            relay(),
            media_type="text/event-stream",
            background=BackgroundTask(upstream.aclose),
        )

    try:
        response = await proxy.client.post(
            "/chat/completions", json=upstream_payload
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="voice_llm_upstream_unavailable"
        ) from exc
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


@router.post("/chat/completions")
async def voice_chat_completions(request: Request):
    _authorize(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_json")

    message = _last_user_message(payload)
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="user_message_required")

    proxy = request.app.state.voice_llm
    if proxy.configured:
        return await _proxy_completion(request, payload)

    # Safe fallback retained for tests and provider-less installations.
    reply = await request.app.state.voice_agent.run(
        message.strip()[:20_000], conversation_id=VOICE_CONVERSATION_ID
    )
    audit(
        "voice_llm_run",
        mode="governed_fallback",
        status=reply.status,
        turns=reply.turns,
        error=reply.error,
        stream=bool(payload.get("stream")),
    )
    text = _spoken_reply(request, reply)
    if reply.status == "completed":
        _schedule_voice_ingestion(request, message, text)
    if payload.get("stream"):
        return StreamingResponse(_sse_stream(text), media_type="text/event-stream")
    return JSONResponse(_completion_json(text))
