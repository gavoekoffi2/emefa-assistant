"""Browser-session activation and revocation API."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from emefa.api.devices import SESSION_COOKIE, current_device, enrollment_guard
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/web/session", tags=["web-session"])


class SessionActivationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enrollment_code: str = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    device_id: str
    name: str


@router.post("", response_model=SessionResponse, status_code=201)
def activate_session(
    payload: SessionActivationRequest,
    request: Request,
    response: Response,
    source: Annotated[str, Depends(enrollment_guard)],
) -> SessionResponse:
    settings = request.app.state.settings
    if settings.enrollment_code is None:
        raise HTTPException(status_code=503, detail="Web activation is not configured")
    if not secrets.compare_digest(payload.enrollment_code, settings.enrollment_code):
        request.app.state.activation_limiter.record_failure(source)
        audit("web_activation_rejected", source=source)
        raise HTTPException(status_code=403, detail="Invalid activation code")
    if request.app.state.devices.count() >= settings.max_devices:
        raise HTTPException(status_code=409, detail="Browser limit reached")

    device, token = request.app.state.devices.enroll(payload.name)
    audit("web_session_activated", device_id=device.device_id, source=source)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return SessionResponse(device_id=device.device_id, name=device.name)


@router.get("", response_model=SessionResponse)
def session_status(device: Annotated[Device, Depends(current_device)]) -> SessionResponse:
    return SessionResponse(device_id=device.device_id, name=device.name)


@router.delete("", status_code=204)
def revoke_session(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    request.app.state.devices.revoke(device.device_id)
    audit("web_session_revoked", device_id=device.device_id)
    response = Response(status_code=204)
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response
