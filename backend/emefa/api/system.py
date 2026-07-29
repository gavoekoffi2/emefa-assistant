"""Honest system status for the HUD — real state, no decorative numbers."""

from contextlib import suppress
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.infrastructure.realtime import SpeechProviderError
from emefa.observability import audit

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


class VoiceCheck(BaseModel):
    """A live answer from the speech provider, for the person who owns it."""

    ok: bool
    configured: bool
    voice_id: str
    reason: str = ""
    provider_status: int | None = None
    #: The provider's own words. Deliberately returned here and nowhere else:
    #: this route is owner-only and the account is theirs, and without it the
    #: only way to diagnose a refusal is to go and read the server log.
    provider_message: str = ""
    available_voices: list[dict[str, str]] = []


@router.get("/voice-check", response_model=VoiceCheck)
async def voice_check(request: Request) -> VoiceCheck:
    """Synthesise one short phrase and report exactly what came back.

    Existed because the alternative was guessing: a refusal in the middle of a
    conversation says the cloned voice stopped, but not whether the key, the
    quota or the voice id is at fault.
    """
    gateway = request.app.state.realtime
    if not gateway.speech_configured:
        return VoiceCheck(
            ok=False,
            configured=False,
            voice_id=gateway.voice_id,
            reason="speech_not_configured",
        )
    try:
        audio = await gateway.synthesize("Bonjour.")
    except SpeechProviderError as error:
        # A wrong voice id is the most common cause, so answer the obvious
        # next question in the same response.
        voices: list[dict[str, str]] = []
        with suppress(Exception):
            voices = await gateway.list_voices()
        audit("voice_check_failed", reason=error.reason, provider_status=error.status_code)
        return VoiceCheck(
            ok=False,
            configured=True,
            voice_id=gateway.voice_id,
            reason=error.reason,
            provider_status=error.status_code,
            provider_message=error.provider_message,
            available_voices=voices,
        )
    except httpx.HTTPError as error:
        return VoiceCheck(
            ok=False,
            configured=True,
            voice_id=gateway.voice_id,
            reason="speech_provider_unavailable",
            provider_message=str(error),
        )
    audit("voice_check_succeeded", bytes_returned=len(audio))
    return VoiceCheck(ok=True, configured=True, voice_id=gateway.voice_id)
