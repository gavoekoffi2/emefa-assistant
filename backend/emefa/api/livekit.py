"""Authenticated LiveKit session broker for the EMEFA voice pilot."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/livekit", tags=["livekit"])


@router.post("/session")
async def create_livekit_session(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, str]:
    broker = request.app.state.livekit
    if not broker.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="livekit_not_configured",
        )
    try:
        ticket = await broker.create_session(device.device_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="livekit_not_configured",
        ) from exc
    audit(
        "livekit_session_issued",
        device_id=device.device_id,
        room=ticket["room"],
    )
    return ticket
