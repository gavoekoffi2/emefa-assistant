"""Assistant identity and business-profile API."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.domain.profiles import (
    ACTIVITY_FIELDS,
    COMPANY_FIELDS,
    FIELD_LABELS,
    OBJECTIVE_FIELDS,
    PERSONAL_FIELDS,
    PREFERENCE_FIELDS,
)
from emefa.observability import audit

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])

Short = Field(default=None, max_length=200)
Long = Field(default=None, max_length=2_000)

#: Fields the configuration centre should render as a textarea.
_LONG_FIELDS = frozenset(
    {
        "offer", "products", "services", "organization", "collaborators",
        "target_customers", "clients", "suppliers", "partners", "goals",
        "annual_goals", "quarterly_goals", "current_priorities", "challenges",
        "organization_preferences", "constraints_notes", "website_summary",
    }
)


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
    """Every field the welcome interview can learn, all of them editable."""

    assistant_id: str
    # Personal
    owner_name: str
    preferred_name: str
    owner_role: str
    country: str
    city: str
    timezone: str
    working_hours: str
    # Company
    company_name: str
    industry: str
    offer: str
    products: str
    services: str
    organization: str
    collaborators: str
    website_url: str
    website_summary: str
    # Activity
    target_customers: str
    clients: str
    suppliers: str
    partners: str
    # Objectives
    goals: str
    annual_goals: str
    quarterly_goals: str
    current_priorities: str
    challenges: str
    # Preferences
    autonomy_level: str
    communication_style: str
    report_frequency: str
    organization_preferences: str
    constraints_notes: str


class BusinessProfileUpdate(BaseModel):
    owner_name: str | None = Short
    preferred_name: str | None = Short
    owner_role: str | None = Short
    country: str | None = Short
    city: str | None = Short
    timezone: str | None = Short
    working_hours: str | None = Short
    company_name: str | None = Short
    industry: str | None = Short
    offer: str | None = Long
    products: str | None = Long
    services: str | None = Long
    organization: str | None = Long
    collaborators: str | None = Long
    target_customers: str | None = Long
    clients: str | None = Long
    suppliers: str | None = Long
    partners: str | None = Long
    goals: str | None = Long
    annual_goals: str | None = Long
    quarterly_goals: str | None = Long
    current_priorities: str | None = Long
    challenges: str | None = Long
    autonomy_level: str | None = Short
    communication_style: str | None = Short
    report_frequency: str | None = Short
    organization_preferences: str | None = Long
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


@router.get("/business/schema")
def business_schema(
    _device: Annotated[Device, Depends(current_device)],
) -> list[dict[str, object]]:
    """Field groups and labels, so the configuration centre stays in sync
    with the interview without duplicating the field list in the frontend."""
    return [
        {
            "group": group,
            "title": title,
            "fields": [
                {"field": field, "label": FIELD_LABELS.get(field, field), "long": field in _LONG_FIELDS}
                for field in fields
            ],
        }
        for group, title, fields in (
            ("personnel", "Profil personnel", PERSONAL_FIELDS),
            ("entreprise", "Entreprise", COMPANY_FIELDS),
            ("activite", "Activité", ACTIVITY_FIELDS),
            ("objectifs", "Objectifs", OBJECTIVE_FIELDS),
            ("preferences", "Préférences de travail", PREFERENCE_FIELDS),
        )
    ]


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
