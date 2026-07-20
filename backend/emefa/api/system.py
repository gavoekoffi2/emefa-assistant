"""Honest system status for the HUD — real state, no decorative numbers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/system", tags=["system"])


class SkillSummary(BaseModel):
    name: str
    risk: str


class SystemStatus(BaseModel):
    brain_configured: bool
    voice_configured: bool
    skills: list[SkillSummary]
    open_task_count: int
    schema_version: int


@router.get("/status", response_model=SystemStatus)
def system_status(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> SystemStatus:
    state = request.app.state
    return SystemStatus(
        brain_configured=state.brain_configured,
        voice_configured=state.realtime.configured,
        skills=[
            SkillSummary(name=tool["name"], risk=tool["risk"])
            for tool in state.agent.tools.describe()
        ],
        open_task_count=len(state.tasks.list_open()),
        schema_version=state.devices.schema_version(),
    )
