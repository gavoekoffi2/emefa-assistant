"""Assistant identity and business-profile API."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
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
    website_url: str
    website_summary: str


class BusinessProfileUpdate(BaseModel):
    owner_name: str | None = Short
    owner_role: str | None = Short
    company_name: str | None = Short
    industry: str | None = Short
    offer: str | None = Long
    target_customers: str | None = Long
    goals: str | None = Long
    constraints_notes: str | None = Long
    website_url: str | None = Field(default=None, max_length=2_000)
    website_summary: str | None = Field(default=None, max_length=8_000)


class WebsiteImportRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2_000)


class WebsiteImportResponse(BaseModel):
    profile: BusinessProfileResponse
    pages_imported: int


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


@router.post("/business/import", response_model=WebsiteImportResponse)
async def import_business_website(
    payload: WebsiteImportRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> WebsiteImportResponse:
    try:
        imported = await request.app.state.website_importer.import_site(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    current = request.app.state.profiles.get_business()
    changes = {
        "website_url": imported.url,
        "website_summary": imported.summary,
    }
    if not current.company_name and imported.company_name:
        changes["company_name"] = imported.company_name
    if not current.offer and imported.description:
        changes["offer"] = imported.description
    profile = request.app.state.profiles.update_business(changes)
    audit(
        "business_website_imported",
        device_id=device.device_id,
        pages_imported=imported.pages_imported,
    )
    return WebsiteImportResponse(
        profile=BusinessProfileResponse(**asdict(profile)),
        pages_imported=imported.pages_imported,
    )
