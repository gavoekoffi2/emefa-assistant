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
    #: The cloned voice is a separate credential from the conversational
    #: agent: it needs a voice id as well as the key. Reporting only
    #: `voice_configured` hid a missing voice id behind a healthy-looking
    #: status, so the first sign of trouble was a refused synthesis.
    cloned_voice_configured: bool
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
        cloned_voice_configured=state.realtime.speech_configured,
        voice_transport=voice_transport,
        livekit_configured=state.livekit.configured,
        skills=[
            SkillSummary(name=tool["name"], risk=tool["risk"])
            for tool in state.agent.tools.describe()
        ],
        open_task_count=len(state.tasks.list_open()),
        schema_version=state.devices.schema_version(),
    )
