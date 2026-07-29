"""Authenticated agent execution and approval API."""

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class EmailSendRequest(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=50_000)

    @field_validator("to")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        recipient = value.strip()
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", recipient):
            raise ValueError("invalid recipient email address")
        return recipient

    @field_validator("subject", "body")
    @classmethod
    def strip_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("email content cannot be blank")
        return content


class PendingActionResponse(BaseModel):
    name: str
    arguments: dict[str, Any]


class RunResponse(BaseModel):
    status: Literal["completed", "confirmation_required", "blocked", "failed", "rejected"]
    turns: int
    answer: str | None = None
    pending_action: PendingActionResponse | None = None
    action_id: str | None = None
    error: str | None = None


class ApprovalSummary(BaseModel):
    action_id: str
    name: str
    arguments: dict[str, Any]
    created_at: str


class DecisionRequest(BaseModel):
    approve: bool


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


def _register_pending(request: Request, device: Device, response: RunResponse) -> RunResponse:
    """Persist a confirmation_required action so it survives reload/restart."""
    if response.status == "confirmation_required" and response.pending_action is not None:
        pending = request.app.state.approvals.create(
            device.device_id,
            RequestedAction(
                name=response.pending_action.name,
                arguments=response.pending_action.arguments,
            ),
        )
        response.action_id = pending.action_id
        audit(
            "approval_created",
            device_id=device.device_id,
            action_id=pending.action_id,
            tool=pending.tool_name,
        )
    return response


@router.post("/runs", response_model=RunResponse)
async def run_agent(
    payload: RunRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> RunResponse:
    reply = await current_workspace(request, device).agent.run(
        payload.message,
        conversation_id=device.device_id,
    )
    audit(
        "agent_run",
        device_id=device.device_id,
        status=reply.status,
        turns=reply.turns,
        error=reply.error,
        pending_action=reply.pending_action.name if reply.pending_action else None,
    )
    return _register_pending(request, device, serialize_reply(reply))


@router.post("/actions/email-send", response_model=RunResponse)
def prepare_email_send(
    payload: EmailSendRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> RunResponse:
    """Prepare a governed email action without another nondeterministic LLM pass."""
    action = RequestedAction(name="email_send", arguments=payload.model_dump())
    response = RunResponse(
        status="confirmation_required",
        turns=0,
        answer="L’e-mail est prêt. Validez la carte d’approbation pour l’envoyer.",
        pending_action=PendingActionResponse(
            name=action.name,
            arguments=action.arguments,
        ),
    )
    audit(
        "email_send_prepared",
        device_id=device.device_id,
        recipient_configured=True,
    )
    return _register_pending(request, device, response)


@router.delete("/conversation", status_code=204)
def clear_conversation(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> None:
    memory = current_workspace(request, device).agent.memory
    forget = getattr(memory, "forget", None)
    if callable(forget):
        forget(device.device_id)
        forget(VOICE_CONVERSATION_ID)
    audit("conversation_cleared", device_id=device.device_id)


@router.get("/approvals", response_model=list[ApprovalSummary])
def list_approvals(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[ApprovalSummary]:
    # Single-user mode: the voice channel has no device binding, so its
    # pending approvals are shown to any authenticated device.
    approvals = request.app.state.approvals
    pending = [
        *approvals.pending_for(device.device_id),
        *approvals.pending_for(VOICE_CONVERSATION_ID),
    ]
    return [
        ApprovalSummary(
            action_id=item.action_id,
            name=item.tool_name,
            arguments=item.arguments,
            created_at=item.created_at,
        )
        for item in pending
    ]


@router.post("/approvals/{action_id}/decision", response_model=RunResponse)
async def decide_approval(
    action_id: str,
    payload: DecisionRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> RunResponse:
    approvals = request.app.state.approvals
    pending = approvals.get(action_id)
    if (
        pending is None
        or pending.conversation_id not in {device.device_id, VOICE_CONVERSATION_ID}
        or pending.status != "pending"
    ):
        raise HTTPException(status_code=404, detail="approval_not_found")

    if not approvals.claim(action_id):
        raise HTTPException(status_code=404, detail="approval_not_found")

    if not payload.approve:
        approvals.resolve(action_id, "rejected")
        audit(
            "approval_rejected",
            device_id=device.device_id,
            action_id=action_id,
            tool=pending.tool_name,
        )
        return RunResponse(
            status="rejected",
            turns=0,
            answer="Action annulée. Rien n’a été exécuté.",
        )

    reply = await current_workspace(request, device).agent.execute_approved(
        pending.to_requested_action(),
        conversation_id=pending.conversation_id,
    )
    approvals.resolve(
        action_id, "executed" if reply.status == "completed" else reply.status
    )
    audit(
        "approval_approved",
        device_id=device.device_id,
        action_id=action_id,
        tool=pending.tool_name,
        result=reply.status,
    )
    return _register_pending(request, device, serialize_reply(reply))
