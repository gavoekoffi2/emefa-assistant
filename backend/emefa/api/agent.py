"""Authenticated agent execution and approval API."""

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.agent import AgentReply, RequestedAction
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.domain.devices import Device
from emefa.domain.visuals import CardCollector
from emefa.observability import audit

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class PendingActionResponse(BaseModel):
    name: str
    arguments: dict[str, Any]


class VisualCardResponse(BaseModel):
    kind: str
    title: str
    caption: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    status: Literal["completed", "confirmation_required", "blocked", "failed", "rejected"]
    turns: int
    answer: str | None = None
    pending_action: PendingActionResponse | None = None
    action_id: str | None = None
    error: str | None = None
    #: What EMEFA chose to show alongside her answer. The interface stays
    #: conversational; a card is an addition to the reply, never a replacement.
    cards: list[VisualCardResponse] = Field(default_factory=list)


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


def schedule_ingestion(request: Request, user_text: str, reply: AgentReply) -> None:
    """Record the exchange and extract durable facts, off the response path.

    Deliberately fire-and-forget: memory is a background benefit, and making
    the user wait for an extraction call — or fail their turn because one
    errored — would trade something they asked for against something they
    did not. The task set holds a strong reference, because a task with no
    referent can be collected before it runs.
    """
    ingestor = getattr(request.app.state, "memory_ingestor", None)
    if ingestor is None or not getattr(request.app.state, "live_extraction", False):
        return
    if reply.status != "completed" or not reply.answer:
        return

    transcript = f"[utilisateur] {user_text}\n[EMEFA] {reply.answer}"
    tasks: set[asyncio.Task[Any]] = request.app.state.background_tasks
    task = asyncio.create_task(ingestor.ingest(transcript, source="chat"))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


@router.post("/runs", response_model=RunResponse)
async def run_agent(
    payload: RunRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> RunResponse:
    # One collector per request: the tool shelf is shared across concurrent
    # requests, so a list on it would hand one user's chart to another.
    with CardCollector() as collector:
        reply = await request.app.state.agent.run(
            payload.message,
            conversation_id=device.device_id,
        )
        cards = collector.summaries()
    schedule_ingestion(request, payload.message, reply)
    audit(
        "agent_run",
        device_id=device.device_id,
        status=reply.status,
        turns=reply.turns,
        error=reply.error,
        pending_action=reply.pending_action.name if reply.pending_action else None,
    )
    response = _register_pending(request, device, serialize_reply(reply))
    response.cards = [VisualCardResponse(**card) for card in cards]
    return response


@router.delete("/conversation", status_code=204)
def clear_conversation(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> None:
    memory = request.app.state.agent.memory
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

    if payload.approve:
        # ADR-005: once a face factor is enrolled, approving a consequential
        # action requires a fresh step-up. Checked before the approval is
        # claimed, so a refusal here leaves it pending rather than consuming it.
        factors = request.app.state.second_factor
        if (
            device.account_id
            and factors.enrolled(device.account_id)
            and not factors.verified_recently(device.device_id)
        ):
            audit(
                "approval_needs_second_factor",
                device_id=device.device_id,
                action_id=action_id,
            )
            raise HTTPException(status_code=403, detail="second_factor_required")

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

    with CardCollector() as collector:
        reply = await request.app.state.agent.execute_approved(
            pending.to_requested_action(),
            conversation_id=pending.conversation_id,
        )
        cards = collector.summaries()
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
    response = _register_pending(request, device, serialize_reply(reply))
    response.cards = [VisualCardResponse(**card) for card in cards]
    return response
