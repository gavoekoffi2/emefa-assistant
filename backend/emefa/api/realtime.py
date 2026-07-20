"""Authenticated session broker for EMEFA's ElevenLabs voice agent."""

from __future__ import annotations

import hashlib
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/realtime", tags=["realtime"])


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
