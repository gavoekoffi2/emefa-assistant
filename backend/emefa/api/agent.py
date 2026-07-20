"""Authenticated agent execution and approval API."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


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
    reply = await request.app.state.agent.run(
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


@router.delete("/conversation", status_code=204)
def clear_conversation(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> None:
    memory = request.app.state.agent.memory
    forget = getattr(memory, "forget", None)
    if callable(forget):
        forget(device.device_id)
    audit("conversation_cleared", device_id=device.device_id)


@router.get("/approvals", response_model=list[ApprovalSummary])
def list_approvals(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[ApprovalSummary]:
    return [
        ApprovalSummary(
            action_id=item.action_id,
            name=item.tool_name,
            arguments=item.arguments,
            created_at=item.created_at,
        )
        for item in request.app.state.approvals.pending_for(device.device_id)
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
        or pending.conversation_id != device.device_id
        or pending.status != "pending"
    ):
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

    reply = await request.app.state.agent.execute_approved(
        pending.to_requested_action(),
        conversation_id=device.device_id,
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
