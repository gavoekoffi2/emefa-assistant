"""Assistant identity and business-profile API."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])

Short = Field(default=None, max_length=200)
Long = Field(default=None, max_length=2_000)


class AssistantProfileResponse(BaseModel):
    assistant_id: str
    name: str
    primary_language: str
    interaction_style: str


class AssistantProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    primary_language: str | None = Field(default=None, min_length=2, max_length=16)
    interaction_style: str | None = Long


class BusinessProfileResponse(BaseModel):
    assistant_id: str
    owner_name: str
    owner_role: str
    company_name: str
    industry: str
    offer: str
    target_customers: str
    goals: str
    constraints_notes: str


class BusinessProfileUpdate(BaseModel):
    owner_name: str | None = Short
    owner_role: str | None = Short
    company_name: str | None = Short
    industry: str | None = Short
    offer: str | None = Long
    target_customers: str | None = Long
    goals: str | None = Long
    constraints_notes: str | None = Long


@router.get("/profile", response_model=AssistantProfileResponse)
def get_profile(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> AssistantProfileResponse:
    profile = request.app.state.profiles.get_assistant()
    return AssistantProfileResponse(**asdict(profile))


@router.patch("/profile", response_model=AssistantProfileResponse)
def update_profile(
    payload: AssistantProfileUpdate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> AssistantProfileResponse:
    changes = payload.model_dump(exclude_none=True)
    profile = request.app.state.profiles.update_assistant(changes)
    audit("assistant_profile_updated", device_id=device.device_id, fields=sorted(changes))
    return AssistantProfileResponse(**asdict(profile))


@router.get("/business", response_model=BusinessProfileResponse)
def get_business(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> BusinessProfileResponse:
    profile = request.app.state.profiles.get_business()
    return BusinessProfileResponse(**asdict(profile))


@router.patch("/business", response_model=BusinessProfileResponse)
def update_business(
    payload: BusinessProfileUpdate,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> BusinessProfileResponse:
    changes = payload.model_dump(exclude_none=True)
    profile = request.app.state.profiles.update_business(changes)
    audit("business_profile_updated", device_id=device.device_id, fields=sorted(changes))
    return BusinessProfileResponse(**asdict(profile))
