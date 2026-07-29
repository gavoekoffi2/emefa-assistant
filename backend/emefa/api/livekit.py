"""Authenticated LiveKit session broker for the EMEFA voice pilot."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/livekit", tags=["livekit"])


class WorkerToolRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class WorkerToolResponse(BaseModel):
    status: str
    answer: str | None = None
    error: str | None = None
    action_id: str | None = None


def _authorize_worker(request: Request) -> None:
    configured = request.app.state.settings.livekit_worker_token
    if configured is None or not configured.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="livekit_worker_not_configured",
        )
    header = request.headers.get("Authorization", "")
    provided = header.removeprefix("Bearer ").strip()
    if not provided or not hmac.compare_digest(
        provided, configured.get_secret_value().strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_livekit_worker_token",
        )


@router.post("/tools/execute", response_model=WorkerToolResponse)
async def execute_worker_tool(
    payload: WorkerToolRequest, request: Request
) -> WorkerToolResponse:
    _authorize_worker(request)
    reply = await request.app.state.voice_agent.run(
        payload.message.strip(), conversation_id=VOICE_CONVERSATION_ID
    )
    action_id: str | None = None
    answer = reply.answer
    if reply.status == "confirmation_required" and reply.pending_action is not None:
        pending = request.app.state.approvals.create(
            VOICE_CONVERSATION_ID, reply.pending_action
        )
        action_id = pending.action_id
        answer = (
            "Cette action attend votre approbation dans l’interface EMEFA. "
            "Je ne l’exécuterai pas sans votre accord explicite."
        )
        audit(
            "approval_created",
            channel="livekit_voice",
            action_id=action_id,
            tool=pending.tool_name,
        )
    audit(
        "livekit_worker_tool",
        status=reply.status,
        turns=reply.turns,
        action_id=action_id,
        error=reply.error,
    )
    return WorkerToolResponse(
        status=reply.status,
        answer=answer,
        error=reply.error,
        action_id=action_id,
    )


@router.post("/session")
async def create_livekit_session(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, str]:
    broker = request.app.state.livekit
    if not broker.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="livekit_not_configured",
        )
    try:
        ticket = await broker.create_session(device.device_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="livekit_not_configured",
        ) from exc
    audit(
        "livekit_session_issued",
        device_id=device.device_id,
        room=ticket["room"],
    )
    return ticket
