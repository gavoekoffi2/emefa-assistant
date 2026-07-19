"""Authenticated agent execution API."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class PendingActionResponse(BaseModel):
    name: str
    arguments: dict[str, Any]


class RunResponse(BaseModel):
    status: Literal["completed", "confirmation_required", "blocked", "failed"]
    turns: int
    answer: str | None = None
    pending_action: PendingActionResponse | None = None
    error: str | None = None


def serialize_reply(reply: AgentReply) -> RunResponse:
    pending = None
    if isinstance(reply.pending_action, RequestedAction):
        pending = PendingActionResponse(
            name=reply.pending_action.name,
            arguments=reply.pending_action.arguments,
        )
    return RunResponse(
        status=reply.status,
        turns=reply.turns,
        answer=reply.answer,
        pending_action=pending,
        error=reply.error,
    )


@router.post("/runs", response_model=RunResponse)
async def run_agent(
    payload: RunRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> RunResponse:
    reply = await request.app.state.agent.run(
        payload.message,
        conversation_id=device.device_id,
    )
    return serialize_reply(reply)
