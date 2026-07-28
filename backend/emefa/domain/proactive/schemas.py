"""Initiatives: what EMEFA decides to do without being asked.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

An initiative is not a notification. A notification says something; an
initiative carries a goal, a permission, a budget, a deadline and a state, and
it stays answerable for what it did. That distinction is the whole reason this
module exists rather than a `send_push()` helper.

Two orthogonal axes govern it, and conflating them is the classic mistake:

* **risk** (`emefa.domain.policy.ActionRisk`) classifies *an action* — sending
  mail is `communicate` whoever asked for it;
* **autonomy** (below) classifies *a decision to act unprompted* — the same
  send is a suggestion at level 1 and an autonomous send at level 5.

Both are enforced. An initiative may never exceed the risk policy, and level 5
always requires a human, whatever the configuration says.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any

from emefa.domain.policy import ActionRisk


class AutonomyLevel(IntEnum):
    """How far EMEFA may go on her own for this initiative."""

    #: Note it, say nothing.
    OBSERVE = 0
    #: Propose it and wait to be asked.
    SUGGEST = 1
    #: Prepare the work — a draft, a document — but do not deliver it.
    PREPARE = 2
    #: Carry out reversible changes to the user's own data.
    EXECUTE_LOCAL = 3
    #: Carry out changes that are awkward to undo.
    EXECUTE_PROJECT = 4
    #: Reach the outside world: send, publish, pay, delete. Never unattended.
    EXTERNAL_ACTION = 5


class InitiativeType(StrEnum):
    REMINDER = "reminder"
    SUGGESTION = "suggestion"
    ALERT = "alert"
    DRAFT = "draft"
    REVIEW = "review"


class InitiativeStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    EXPIRED = "expired"
    FAILED = "failed"


#: Statuses that no longer need the user's attention.
CLOSED_STATUSES = frozenset(
    {
        InitiativeStatus.COMPLETED,
        InitiativeStatus.DISMISSED,
        InitiativeStatus.EXPIRED,
        InitiativeStatus.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class Initiative:
    initiative_id: str
    type: InitiativeType
    title: str
    #: What triggered it, in the user's terms. Shown, not logged.
    reason: str
    #: The single concrete next step. Vague initiatives are noise.
    next_action: str
    autonomy_level: AutonomyLevel = AutonomyLevel.SUGGEST
    risk: ActionRisk = ActionRisk.OBSERVE
    status: InitiativeStatus = InitiativeStatus.PENDING
    #: Stable key identifying *the same concern*, so a signal that persists
    #: for a week does not produce seven identical cards.
    dedupe_key: str = ""
    #: Ceiling for any model work this initiative causes. None means it does
    #: no model work at all — most do not.
    cost_max_tokens: int | None = None
    deadline: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    resolved_at: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "initiative_id": self.initiative_id,
            "type": self.type.value,
            "title": self.title,
            "reason": self.reason,
            "next_action": self.next_action,
            "autonomy_level": int(self.autonomy_level),
            "risk": self.risk.value,
            "status": self.status.value,
            "requires_validation": needs_human_validation(self),
            "deadline": self.deadline,
            "created_at": self.created_at,
        }


def needs_human_validation(initiative: Initiative) -> bool:
    """Whether a human must approve before this initiative acts.

    Level 5 — send, publish, pay, delete — always returns True. It is not a
    default that configuration can loosen: those are the acts that cannot be
    taken back, and an assistant that can perform them unattended is one
    mistake away from being untrustworthy.

    Below that, anything the risk policy would not run unattended also needs a
    human, so the two systems cannot disagree.
    """
    if initiative.autonomy_level >= AutonomyLevel.EXTERNAL_ACTION:
        return True
    from emefa.domain.policy import Decision, decide

    return decide(initiative.risk) is not Decision.RUN
