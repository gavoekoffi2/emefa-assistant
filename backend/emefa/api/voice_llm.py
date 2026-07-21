"""ElevenLabs Custom-LLM endpoint, routed through the governed EMEFA engine.

Each voice turn runs AgentEngine.run() on the shared voice conversation:
the voice gets the same skills, risk policy, and approval loop as text.
Consequential actions are never executed from the voice channel directly —
they become pending approvals announced orally and decided in the HUD.
"""

import hmac
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.observability import audit

router = APIRouter(prefix="/v1/voice-llm", tags=["voice-llm"])

_ERROR_SPOKEN = {
    "brain_unavailable": "Le moteur de langage est indisponible pour le moment. Réessayons dans un instant.",
    "unknown_tool": "J’ai tenté une action que je ne connais pas. Reformulez votre demande.",
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
    return _ERROR_SPOKEN.get(reply.error or "", "La demande n’a pas abouti. Réessayez.")


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
                {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]},
                ensure_ascii=False,
            )
            yield f"data: {data}\n\n".encode()
        yield b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"

    return generate()


@router.post("/chat/completions")
async def voice_chat_completions(request: Request):
    _authorize(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_json")
    message = next(
        (
            item.get("content")
            for item in reversed(payload.get("messages") or [])
            if item.get("role") == "user" and isinstance(item.get("content"), str)
        ),
        None,
    )
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="user_message_required")

    reply = await request.app.state.voice_agent.run(
        message.strip()[:20_000], conversation_id=VOICE_CONVERSATION_ID
    )
    audit(
        "voice_llm_run",
        status=reply.status,
        turns=reply.turns,
        error=reply.error,
        stream=bool(payload.get("stream")),
    )
    text = _spoken_reply(request, reply)
    if payload.get("stream"):
        return StreamingResponse(_sse_stream(text), media_type="text/event-stream")
    return JSONResponse(_completion_json(text))
