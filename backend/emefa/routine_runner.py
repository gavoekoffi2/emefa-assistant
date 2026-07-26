"""Execution service for governed routines."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from emefa.domain.agent import AgentEngine, AgentReply
from emefa.domain.approvals import ApprovalRepository
from emefa.domain.command_center import Routine, RoutineRepository, RoutineRun
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.observability import audit


async def execute_routine(
    routine: Routine,
    repository: RoutineRepository,
    agent: AgentEngine,
    approvals: ApprovalRepository,
    conversation_id: str,
) -> RoutineRun:
    """Execute one routine and persist an honest, approval-aware receipt."""
    run = repository.start_run(routine.routine_id)
    try:
        reply: AgentReply = await agent.run(routine.prompt, conversation_id=conversation_id)
    except Exception:  # noqa: BLE001 - isolate one routine from the scheduler/API
        audit("routine_failed", routine_id=routine.routine_id, run_id=run.run_id)
        return repository.finish_run(run.run_id, "failed", "agent_unavailable")

    action_id: str | None = None
    result = reply.answer or reply.error or ""
    status = reply.status
    if reply.status == "confirmation_required" and reply.pending_action is not None:
        pending = approvals.create(conversation_id, reply.pending_action)
        action_id = pending.action_id
        result = "Action préparée et placée en attente de votre approbation."
        status = "awaiting_approval"
    audit(
        "routine_finished",
        routine_id=routine.routine_id,
        run_id=run.run_id,
        status=status,
        action_id=action_id,
    )
    return repository.finish_run(run.run_id, status, result, action_id)


async def routine_scheduler_loop(
    routines: RoutineRepository,
    agent: AgentEngine,
    approvals: ApprovalRepository,
    *,
    timezone_name: str = "Africa/Lome",
    poll_seconds: float = 60.0,
) -> None:
    """Run due routines once per local calendar slot.

    A routine can ask the agent to prepare work, but consequential tools still
    enter the same approval queue as direct voice/text requests.
    """
    timezone = ZoneInfo(timezone_name)
    while True:
        try:
            now = datetime.now(timezone)
            for routine in routines.due(now):
                await execute_routine(
                    routine,
                    routines,
                    agent,
                    approvals,
                    VOICE_CONVERSATION_ID,
                )
        except Exception:  # noqa: BLE001 - a failed tick must not stop future ticks
            audit("routine_scheduler_iteration_failed")
        await asyncio.sleep(max(15.0, poll_seconds))
