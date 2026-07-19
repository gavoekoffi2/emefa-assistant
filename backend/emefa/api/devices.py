"""Device enrollment and authentication API."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/devices", tags=["devices"])
bearer = HTTPBearer(auto_error=False)
SESSION_COOKIE = "emefa_session"


class EnrollmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enrollment_code: str = Field(min_length=1, max_length=256)


class EnrollmentResponse(BaseModel):
    device_id: str
    token: str


class DeviceResponse(BaseModel):
    device_id: str
    name: str


def current_device(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Device:
    token = credentials.credentials if credentials is not None else request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device session required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device = request.app.state.devices.authenticate(token)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return device


@router.post("/enroll", response_model=EnrollmentResponse, status_code=201)
def enroll(payload: EnrollmentRequest, request: Request) -> EnrollmentResponse:
    settings = request.app.state.settings
    if settings.enrollment_code is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device enrollment is not configured",
        )
    if not secrets.compare_digest(payload.enrollment_code, settings.enrollment_code):
        raise HTTPException(status_code=403, detail="Invalid enrollment code")
    if request.app.state.devices.count() >= settings.max_devices:
        raise HTTPException(status_code=409, detail="Device limit reached")
    device, token = request.app.state.devices.enroll(payload.name)
    return EnrollmentResponse(device_id=device.device_id, token=token)


@router.get("/me", response_model=DeviceResponse)
def me(device: Annotated[Device, Depends(current_device)]) -> DeviceResponse:
    return DeviceResponse(device_id=device.device_id, name=device.name)


@router.delete("/me", status_code=204)
def revoke_me(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    request.app.state.devices.revoke(device.device_id)
    return Response(status_code=204)
