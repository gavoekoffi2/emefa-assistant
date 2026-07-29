"""Skill catalogue and per-assistant enablement API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/skills", tags=["skills"])


class SkillToggleResponse(BaseModel):
    name: str
    enabled: bool


@router.get("")
def list_skills(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    registry = request.app.state.skills
    return {
        "skills": [status.summary() for status in registry.catalogue()],
        # Contributions that failed to load are reported, not hidden: a skill
        # silently missing is harder to diagnose than one marked broken.
        "errors": registry.errors,
    }


@router.post("/{name}/enable", response_model=SkillToggleResponse)
def enable_skill(
    name: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> SkillToggleResponse:
    registry = request.app.state.skills
    status = registry.status(name)
    if status is None:
        raise HTTPException(status_code=404, detail="skill_not_found")
    if status.blocked_reason is not None:
        raise HTTPException(status_code=409, detail=status.blocked_reason)
    registry.enable(name)
    audit("skill_enabled", device_id=device.device_id, skill=name)
    return SkillToggleResponse(name=name, enabled=True)


@router.post("/{name}/disable", response_model=SkillToggleResponse)
def disable_skill(
    name: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> SkillToggleResponse:
    registry = request.app.state.skills
    if registry.status(name) is None:
        raise HTTPException(status_code=404, detail="skill_not_found")
    registry.disable(name)
    audit("skill_disabled", device_id=device.device_id, skill=name)
    return SkillToggleResponse(name=name, enabled=False)
