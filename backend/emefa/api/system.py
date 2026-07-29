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
    voice_transport: str
    livekit_configured: bool
    skills: list[SkillSummary]
    open_task_count: int
    schema_version: int


@router.get("/status", response_model=SystemStatus)
def system_status(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> SystemStatus:
    state = request.app.state
    voice_transport = state.settings.voice_transport
    return SystemStatus(
        brain_configured=state.brain_configured,
        voice_configured=(
            state.livekit.configured if voice_transport == "livekit" else state.realtime.configured
        ),
        voice_transport=voice_transport,
        livekit_configured=state.livekit.configured,
        skills=[
            SkillSummary(name=tool["name"], risk=tool["risk"])
            for tool in state.agent.tools.describe()
        ],
        open_task_count=len(state.tasks.list_open()),
        schema_version=state.devices.schema_version(),
    )


@router.get("/budget")
def budget_report(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict:
    """Today's token spend per scope.

    `pricing_configured` is false until the owner enters their provider's real
    prices; the UI must then show tokens rather than a confident 0,00 $.
    """
    return request.app.state.budget.report()
