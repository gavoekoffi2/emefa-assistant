"""Missions: multi-step work that survives the request that started it.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

`AgentEngine` answers a message in at most four turns, inside one HTTP
request. That is right for "what's on my agenda" and wrong for "prépare la
proposition pour la clinique et relance-les" — work with an order to it, steps
that can fail individually, and a point where the user must be asked.

A mission is that work made durable and inspectable. Its state lives in the
database after every step, so:

* a crash, a deploy or a lost connection resumes instead of restarting;
* a step needing approval waits without holding anything open;
* a partially completed mission reports as partially completed, not as done.

The status vocabulary is CLAUDE.md §25's, and it exists because "completed"
must mean the work happened, not that a model produced encouraging text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class MissionStatus(StrEnum):
    PLANNED = "planned"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    #: Some steps succeeded, some did not. Deliberately distinct from failed:
    #: the user needs to know what *did* happen.
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    #: Executed, and the verification agreed it did what it claimed. Only a
    #: verified step counts towards a completed mission.
    VERIFIED = "verified"
    #: Executed, but verification could not confirm it. Not a success.
    UNVERIFIED = "unverified"
    FAILED = "failed"
    SKIPPED = "skipped"


TERMINAL_STEP_STATUSES = frozenset(
    {StepStatus.VERIFIED, StepStatus.UNVERIFIED, StepStatus.FAILED, StepStatus.SKIPPED}
)
TERMINAL_MISSION_STATUSES = frozenset(
    {
        MissionStatus.COMPLETED,
        MissionStatus.PARTIALLY_COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    }
)

#: Hard ceiling on a plan. A twenty-step plan from a language model is not a
#: plan, it is a list.
MAX_STEPS = 8
#: Attempts per step before the mission gives up on it. Retrying forever is
#: how an autonomous loop burns a budget on a permanent failure.
MAX_ATTEMPTS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Step:
    step_id: str
    mission_id: str
    position: int
    #: What this step is for, in the user's terms. Shown when approval is
    #: requested, so it has to be readable.
    description: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    #: What "this worked" means, written when the step was planned. A step
    #: without one can only ever be verified as "the call returned something".
    success_criteria: str = ""
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] | None = None
    #: Why the verifier accepted or rejected the result.
    verification: str = ""
    error: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def summary(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "position": self.position,
            "description": self.description,
            "tool": self.tool_name,
            "success_criteria": self.success_criteria,
            "status": self.status.value,
            "attempts": self.attempts,
            "verification": self.verification,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class Mission:
    mission_id: str
    goal: str
    status: MissionStatus = MissionStatus.PLANNED
    conversation_id: str = ""
    error: str = ""
    #: Which planning strategy produced this mission.
    strategy: str = "manual"
    #: Questions the planner could not answer from context. A mission with
    #: open questions is not executable: EMEFA asks rather than guessing.
    missing_information: tuple[str, ...] = ()
    #: Ceiling on model spend for this mission specifically, on top of the
    #: scope budget.
    max_tokens: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    steps: tuple[Step, ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "strategy": self.strategy,
            "missing_information": list(self.missing_information),
            "executable": not self.missing_information,
            "steps": [step.summary() for step in self.steps],
            "progress": self.progress(),
        }

    def progress(self) -> dict[str, int]:
        counts = {"total": len(self.steps), "verified": 0, "failed": 0, "pending": 0}
        for step in self.steps:
            if step.status is StepStatus.VERIFIED:
                counts["verified"] += 1
            elif step.status in {StepStatus.FAILED, StepStatus.UNVERIFIED}:
                counts["failed"] += 1
            elif step.status not in TERMINAL_STEP_STATUSES:
                counts["pending"] += 1
        return counts

    def next_step(self) -> Step | None:
        for step in sorted(self.steps, key=lambda item: item.position):
            if step.status not in TERMINAL_STEP_STATUSES:
                return step
        return None


def outcome_for(mission: Mission) -> MissionStatus:
    """The honest status for a mission whose steps have all finished.

    `completed` requires every step verified. Anything less is
    `partially_completed` or `failed` — never "done with caveats", which is
    how an assistant ends up reporting work it did not do (CLAUDE.md §25).
    """
    progress = mission.progress()
    if progress["pending"]:
        return mission.status
    if progress["failed"] == 0 and progress["verified"] == progress["total"]:
        return MissionStatus.COMPLETED
    if progress["verified"] == 0:
        return MissionStatus.FAILED
    return MissionStatus.PARTIALLY_COMPLETED
