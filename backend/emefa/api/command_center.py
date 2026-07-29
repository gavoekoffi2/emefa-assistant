"""Authenticated command-center API for initiatives and governed routines."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.command_center import (
    INITIATIVE_STATUSES,
    Initiative,
    Routine,
)
from emefa.domain.conversations import VOICE_CONVERSATION_ID
from emefa.domain.devices import Device
from emefa.observability import audit
from emefa.routine_runner import execute_routine

router = APIRouter(prefix="/v1/command-center", tags=["command-center"])


class InitiativeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(default="", max_length=5_000)
    status: str = Field(default="proposed", pattern="^(proposed|active|paused|completed|cancelled)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    risk: str = Field(default="low", pattern="^(low|medium|high)$")
    autonomy_level: int = Field(default=0, ge=0, le=3)
    next_action: str = Field(default="", max_length=2_000)
    due_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class InitiativeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = Field(default=None, max_length=5_000)
    status: str | None = Field(default=None, pattern="^(proposed|active|paused|completed|cancelled)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|critical)$")
    risk: str | None = Field(default=None, pattern="^(low|medium|high)$")
    autonomy_level: int | None = Field(default=None, ge=0, le=3)
    next_action: str | None = Field(default=None, max_length=2_000)
    due_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class RoutineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=10_000)
    schedule_kind: str = Field(default="manual", pattern="^(manual|daily|weekly)$")
    schedule_hour: int | None = Field(default=None, ge=0, le=23)
    schedule_weekday: int | None = Field(default=None, ge=0, le=6)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.schedule_kind in {"daily", "weekly"} and self.schedule_hour is None:
            raise ValueError("schedule_hour_required")
        if self.schedule_kind == "weekly" and self.schedule_weekday is None:
            raise ValueError("schedule_weekday_required")
        if self.schedule_kind == "manual":
            self.schedule_hour = None
            self.schedule_weekday = None
        if self.schedule_kind == "daily":
            self.schedule_weekday = None
        return self


class RoutineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, min_length=1, max_length=10_000)
    schedule_kind: str | None = Field(default=None, pattern="^(manual|daily|weekly)$")
    schedule_hour: int | None = Field(default=None, ge=0, le=23)
    schedule_weekday: int | None = Field(default=None, ge=0, le=6)
    enabled: bool | None = None


@router.get("/snapshot")
def snapshot(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    state = request.app.state
    initiatives = state.initiatives.list(include_closed=False)
    initiative_counts = {status: 0 for status in INITIATIVE_STATUSES}
    for item in state.initiatives.list():
        initiative_counts[item.status] += 1
    pending = [
        *state.approvals.pending_for(device.device_id),
        *state.approvals.pending_for(VOICE_CONVERSATION_ID),
    ]
    return {
        "captured_at": __import__("datetime").datetime.now().isoformat(),
        "initiatives": [asdict(item) for item in initiatives],
        "initiative_counts": initiative_counts,
        "open_task_count": len(state.tasks.list_open()),
        "prospect_count": len(state.prospects.list_open()),
        "due_follow_up_count": len(state.prospects.due_follow_ups()),
        "active_routine_count": len(state.routines.list(enabled_only=True)),
        "pending_approval_count": len({item.action_id for item in pending}),
        "skill_count": len(state.agent.tools.describe()),
        "recent_runs": [asdict(item) for item in state.routines.list_runs(limit=10)],
    }


@router.get("/initiatives", response_model=list[Initiative])
def list_initiatives(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    include_closed: bool = True,
) -> list[Initiative]:
    return current_workspace(request, device).initiatives.list(include_closed=include_closed)


@router.post("/initiatives", response_model=Initiative, status_code=201)
def create_initiative(
    payload: InitiativeCreate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Initiative:
    item = current_workspace(request, device).initiatives.add(**payload.model_dump())
    audit("initiative_created", device_id=device.device_id, initiative_id=item.initiative_id)
    return item


@router.patch("/initiatives/{initiative_id}", response_model=Initiative)
def update_initiative(
    initiative_id: str,
    payload: InitiativeUpdate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Initiative:
    changes = payload.model_dump(exclude_unset=True)
    item = current_workspace(request, device).initiatives.update(initiative_id, changes)
    if item is None:
        raise HTTPException(status_code=404, detail="initiative_not_found")
    audit("initiative_updated", device_id=device.device_id, initiative_id=initiative_id)
    return item


@router.get("/routines", response_model=list[Routine])
def list_routines(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[Routine]:
    return current_workspace(request, device).routines.list()


@router.post("/routines", response_model=Routine, status_code=201)
def create_routine(
    payload: RoutineCreate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Routine:
    item = current_workspace(request, device).routines.add(**payload.model_dump())
    audit("routine_created", device_id=device.device_id, routine_id=item.routine_id)
    return item


@router.patch("/routines/{routine_id}", response_model=Routine)
def update_routine(
    routine_id: str,
    payload: RoutineUpdate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Routine:
    routines = current_workspace(request, device).routines
    current = routines.get(routine_id)
    if current is None:
        raise HTTPException(status_code=404, detail="routine_not_found")
    changes = payload.model_dump(exclude_unset=True)
    schedule_kind = changes.get("schedule_kind", current.schedule_kind)
    schedule_hour = changes.get("schedule_hour", current.schedule_hour)
    schedule_weekday = changes.get("schedule_weekday", current.schedule_weekday)
    if schedule_kind in {"daily", "weekly"} and schedule_hour is None:
        raise HTTPException(status_code=422, detail="schedule_hour_required")
    if schedule_kind == "weekly" and schedule_weekday is None:
        raise HTTPException(status_code=422, detail="schedule_weekday_required")
    if schedule_kind == "manual":
        changes.update(schedule_hour=None, schedule_weekday=None)
    elif schedule_kind == "daily":
        changes["schedule_weekday"] = None
    item = routines.update(routine_id, changes)
    assert item is not None
    audit("routine_updated", device_id=device.device_id, routine_id=routine_id)
    return item


@router.post("/routines/{routine_id}/run")
async def run_routine_now(
    routine_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    workspace = current_workspace(request, device)
    routine = workspace.routines.get(routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="routine_not_found")
    run = await execute_routine(
        routine,
        workspace.routines,
        workspace.agent,
        workspace.approvals,
        device.device_id,
    )
    return asdict(run)
