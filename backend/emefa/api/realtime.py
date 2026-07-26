"""Authenticated session broker for EMEFA's ElevenLabs voice agent."""

from __future__ import annotations

import hashlib
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/realtime", tags=["realtime"])


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=900)


@router.get("/session")
async def create_realtime_session(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, str]:
    gateway = request.app.state.realtime
    if not gateway.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="realtime_not_configured",
        )
    safety_identifier = hashlib.sha256(device.device_id.encode("utf-8")).hexdigest()
    try:
        signed_url = await gateway.get_signed_url(safety_identifier)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="realtime_provider_rejected_session") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="realtime_provider_unavailable") from exc
    audit("realtime_session_issued", device_id=device.device_id)
    return {"signed_url": signed_url}


@router.post("/speech", response_class=Response)
async def create_speech(
    payload: SpeechRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    gateway = request.app.state.realtime
    if not gateway.speech_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="speech_not_configured",
        )
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="speech_text_empty")
    try:
        audio = await gateway.synthesize(text)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="speech_provider_rejected_request") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="speech_provider_unavailable") from exc
    audit("cloned_speech_generated", device_id=device.device_id, character_count=len(text))
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
