"""Mission API — plan, advance, approve, cancel."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.domain.missions import MAX_STEPS
from emefa.observability import audit

router = APIRouter(prefix="/v1/missions", tags=["missions"])


class PlannedStep(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    tool: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MissionRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2_000)
    steps: list[PlannedStep] = Field(min_length=1, max_length=MAX_STEPS)


class PlanRequestBody(BaseModel):
    goal: str = Field(min_length=3, max_length=2_000)
    #: Anything the caller already knows — a client name lifted from the
    #: conversation, a date. Fills template placeholders so EMEFA does not have
    #: to ask for what was already said.
    context: dict[str, str] = Field(default_factory=dict)
    #: Store the plan as a mission. False returns the plan for review without
    #: committing to it.
    save: bool = True


@router.get("")
def list_missions(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    return {
        "missions": [
            mission.summary() for mission in request.app.state.missions.list_recent()
        ]
    }


@router.post("", status_code=201)
def create_mission(
    payload: MissionRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    """Record a plan. Deliberately does not start it: planning and executing
    are separate decisions, and only the second spends anything."""
    unknown = [
        step.tool for step in payload.steps if request.app.state.agent.tools.get(step.tool) is None
    ]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown_tools:{','.join(unknown)}")

    mission = request.app.state.missions.create(
        payload.goal,
        [(step.description, step.tool, step.arguments) for step in payload.steps],
        conversation_id=device.device_id,
    )
    audit("mission_created", device_id=device.device_id, mission_id=mission.mission_id)
    return mission.summary()


@router.post("/plan", status_code=201)
async def plan_mission(
    payload: PlanRequestBody,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    """Turn a sentence into a plan.

    The plan is stored but never started: planning and executing are separate
    decisions, and only the second spends anything or touches the user's data.

    A plan may come back with `missing_information` — "de quel client
    s'agit-il ?". That is the honest outcome for an ambiguous request, and the
    orchestrator refuses to run such a mission, so EMEFA asks instead of
    guessing.
    """
    plan = await request.app.state.planner.plan(payload.goal, payload.context)
    audit(
        "mission_planned",
        device_id=device.device_id,
        strategy=plan.strategy,
        steps=len(plan.steps),
        executable=plan.executable,
    )
    if not payload.save or not plan.steps:
        return {"plan": plan.summary(), "mission": None}

    mission = request.app.state.missions.create(
        plan.goal,
        list(plan.steps),
        conversation_id=device.device_id,
        strategy=plan.strategy,
        missing_information=plan.missing_information,
    )
    return {"plan": plan.summary(), "mission": mission.summary()}


@router.get("/{mission_id}")
def get_mission(
    mission_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    mission = request.app.state.missions.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission_not_found")
    return mission.summary()


@router.post("/{mission_id}/advance")
async def advance_mission(
    mission_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    """Run the mission until it finishes or needs the user.

    Bounded by the orchestrator, so a request can never turn into an
    open-ended agent loop.
    """
    mission = await request.app.state.mission_orchestrator.run_to_completion(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission_not_found")
    audit(
        "mission_advanced",
        device_id=device.device_id,
        mission_id=mission_id,
        status=mission.status.value,
    )
    return mission.summary()


@router.post("/{mission_id}/steps/{step_id}/approve")
async def approve_step(
    mission_id: str,
    step_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    outcome = await request.app.state.mission_orchestrator.approve_step(mission_id, step_id)
    if outcome is None or outcome.mission is None:
        raise HTTPException(status_code=404, detail="mission_not_found")
    audit(
        "mission_step_approved",
        device_id=device.device_id,
        mission_id=mission_id,
        step_id=step_id,
    )
    return outcome.mission.summary()


@router.post("/{mission_id}/cancel")
def cancel_mission(
    mission_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    mission = request.app.state.mission_orchestrator.cancel(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission_not_found")
    audit("mission_cancelled", device_id=device.device_id, mission_id=mission_id)
    return mission.summary()
