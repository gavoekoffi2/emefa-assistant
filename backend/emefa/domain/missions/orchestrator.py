"""Running a mission, one durable step at a time.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

`advance()` executes at most one step and returns. Everything it learned is in
the database before it returns, which is what makes resume free: picking a
mission back up after a crash, a deploy or an approval is the same call.

The risk policy governs here exactly as it does in a chat turn — the same
`decide()`, the same three outcomes — because a mission is not a way to reach
tools the user would otherwise be asked about. A step whose tool the policy
blocks fails the mission; one it would ask about waits for the user.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from emefa.domain.agent import ToolShelf
from emefa.domain.missions.schemas import (
    MAX_ATTEMPTS,
    Mission,
    MissionStatus,
    StepStatus,
    outcome_for,
)
from emefa.domain.missions.store import MissionRepository
from emefa.domain.missions.verifier import StepVerifier
from emefa.domain.policy import Decision, decide


@dataclass(frozen=True, slots=True)
class StepOutcome:
    mission: Mission
    #: What happened to the step that was just attempted, or None when the
    #: mission had nothing left to do.
    step_status: StepStatus | None = None
    detail: str = ""


class MissionOrchestrator:
    def __init__(
        self,
        missions: MissionRepository,
        tools: ToolShelf,
        verifier: StepVerifier | None = None,
    ) -> None:
        self.missions = missions
        self.tools = tools
        self.verifier = verifier or StepVerifier()

    async def advance(self, mission_id: str) -> StepOutcome | None:
        mission = self.missions.get(mission_id)
        if mission is None:
            return None
        if mission.status in {MissionStatus.CANCELLED, MissionStatus.FAILED}:
            return StepOutcome(mission, None, "mission close")
        if mission.missing_information:
            # The planner could not answer something the plan depends on.
            # Executing anyway would mean acting on a guess, which is the one
            # thing a plan carrying open questions must never do.
            return StepOutcome(
                mission, None, "informations manquantes : " + " ".join(mission.missing_information)
            )

        step = mission.next_step()
        if step is None:
            return StepOutcome(self._settle(mission), None, "aucune étape restante")

        tool = self.tools.get(step.tool_name)
        if tool is None:
            # A plan naming a tool that does not exist is a planning failure,
            # and retrying it would never help.
            self.missions.update_step(
                step.step_id, StepStatus.FAILED, error=f"outil inconnu : {step.tool_name}"
            )
            return StepOutcome(
                self._settle(self.missions.get(mission_id)), StepStatus.FAILED, "outil inconnu"
            )

        decision = decide(tool.risk)
        if decision is Decision.BLOCK:
            self.missions.update_step(
                step.step_id, StepStatus.FAILED, error="action interdite par la politique"
            )
            mission = self.missions.set_mission_status(
                mission_id, MissionStatus.FAILED, "action interdite par la politique"
            )
            return StepOutcome(mission, StepStatus.FAILED, "risque interdit")
        if decision is Decision.ASK:
            # Persisted and abandoned, not held: the user may take a day, and
            # nothing should be waiting on them in memory.
            self.missions.update_step(step.step_id, StepStatus.AWAITING_APPROVAL)
            mission = self.missions.set_mission_status(
                mission_id, MissionStatus.AWAITING_APPROVAL
            )
            return StepOutcome(mission, StepStatus.AWAITING_APPROVAL, step.description)

        self.missions.set_mission_status(mission_id, MissionStatus.EXECUTING)
        return await self._execute(mission_id, step.step_id)

    async def approve_step(self, mission_id: str, step_id: str) -> StepOutcome | None:
        """Run a step the user has just authorised.

        The risk check is not repeated as a gate — the user has answered it —
        but a blocked class is still refused: approval is consent to an action
        the policy allows, not a way around the policy.
        """
        mission = self.missions.get(mission_id)
        if mission is None:
            return None
        step = next((item for item in mission.steps if item.step_id == step_id), None)
        if step is None or step.status is not StepStatus.AWAITING_APPROVAL:
            return StepOutcome(mission, None, "étape non en attente d'accord")
        tool = self.tools.get(step.tool_name)
        if tool is None or decide(tool.risk) is Decision.BLOCK:
            self.missions.update_step(
                step_id, StepStatus.FAILED, error="action interdite par la politique"
            )
            return StepOutcome(
                self._settle(self.missions.get(mission_id)), StepStatus.FAILED, "risque interdit"
            )
        self.missions.set_mission_status(mission_id, MissionStatus.EXECUTING)
        return await self._execute(mission_id, step_id)

    def cancel(self, mission_id: str) -> Mission | None:
        return self.missions.set_mission_status(mission_id, MissionStatus.CANCELLED)

    async def run_to_completion(self, mission_id: str, max_steps: int = 8) -> Mission | None:
        """Drive a mission until it finishes, needs the user, or hits the step
        ceiling. Bounded because an unbounded loop over model-planned steps is
        the shape of every runaway agent (CLAUDE.md §34)."""
        for _ in range(max_steps):
            outcome = await self.advance(mission_id)
            if outcome is None:
                return None
            if outcome.mission.status in {
                MissionStatus.AWAITING_APPROVAL,
                MissionStatus.COMPLETED,
                MissionStatus.PARTIALLY_COMPLETED,
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            }:
                return outcome.mission
        return self.missions.get(mission_id)

    # ── internals ─────────────────────────────────────────────────────────

    async def _execute(self, mission_id: str, step_id: str) -> StepOutcome:
        mission = self.missions.get(mission_id)
        assert mission is not None
        step = next(item for item in mission.steps if item.step_id == step_id)
        tool = self.tools.get(step.tool_name)
        assert tool is not None

        try:
            output = tool.handler(step.arguments)
            if inspect.isawaitable(output):
                output = await output
            result = dict(output) if output is not None else None
        except ValueError as error:
            return self._fail_step(mission_id, step_id, f"arguments invalides : {error}")
        except Exception as error:
            return self._fail_step(mission_id, step_id, f"échec : {type(error).__name__}")

        verdict = self.verifier.verify(
            step.tool_name,
            step.success_criteria or step.description,
            step.arguments,
            result,
        )
        if verdict.ok:
            self.missions.update_step(
                step_id,
                StepStatus.VERIFIED,
                result=result,
                verification=f"{verdict.method} — {verdict.reason}",
                increment_attempt=True,
            )
            return StepOutcome(
                self._settle(self.missions.get(mission_id)),
                StepStatus.VERIFIED,
                verdict.reason,
            )

        # Verification failed. Retry while attempts remain — a transient
        # failure is common — then record the step as unverified, which is
        # explicitly not a success.
        attempts = step.attempts + 1
        final = attempts >= MAX_ATTEMPTS
        self.missions.update_step(
            step_id,
            StepStatus.UNVERIFIED if final else StepStatus.PENDING,
            result=result,
            verification=f"{verdict.method} — {verdict.reason}",
            error="" if final else "non vérifié, nouvelle tentative",
            increment_attempt=True,
        )
        return StepOutcome(
            self._settle(self.missions.get(mission_id)) if final else self.missions.get(mission_id),
            StepStatus.UNVERIFIED if final else StepStatus.PENDING,
            verdict.reason,
        )

    def _fail_step(self, mission_id: str, step_id: str, message: str) -> StepOutcome:
        mission = self.missions.get(mission_id)
        assert mission is not None
        step = next(item for item in mission.steps if item.step_id == step_id)
        final = step.attempts + 1 >= MAX_ATTEMPTS
        self.missions.update_step(
            step_id,
            StepStatus.FAILED if final else StepStatus.PENDING,
            error=message,
            increment_attempt=True,
        )
        updated = self.missions.get(mission_id)
        return StepOutcome(
            self._settle(updated) if final else updated,
            StepStatus.FAILED if final else StepStatus.PENDING,
            message,
        )

    def _settle(self, mission: Mission | None) -> Mission | None:
        """Give the mission the status its steps actually earned."""
        if mission is None:
            return None
        resolved = outcome_for(mission)
        if resolved is mission.status:
            return mission
        return self.missions.set_mission_status(mission.mission_id, resolved)
