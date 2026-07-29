"""Read API for the proactive daily briefing and the evening report.

``/today`` returns the *stored* brief produced by the scheduler, and 404s when
no job has run. ``/morning`` and ``/evening`` compose live, because both are
deterministic database reads: the interface can always show an executive their
current situation without waiting for a scheduled hour.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.devices import Device
from emefa.domain.reports import (
    EVENING_SECTIONS,
    MORNING_SECTIONS,
    compose_evening_report,
    compose_morning_brief,
    format_evening_text,
    format_morning_text,
)
from emefa.observability import audit

router = APIRouter(prefix="/v1/briefings", tags=["briefings"])


class BriefingResponse(BaseModel):
    brief_date: str
    content: dict[str, Any]
    text: str
    emailed: bool
    created_at: str


class ComposedReport(BaseModel):
    brief_date: str
    content: dict[str, Any]
    text: str


class SectionPreferences(BaseModel):
    morning_sections: list[str] | None = Field(default=None, max_length=40)
    evening_sections: list[str] | None = Field(default=None, max_length=40)


class PreferencesResponse(BaseModel):
    morning_sections: list[str]
    evening_sections: list[str]
    available_morning: list[dict[str, str]]
    available_evening: list[dict[str, str]]


@router.get("/today", response_model=BriefingResponse)
def todays_briefing(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> BriefingResponse:
    briefing = current_workspace(request, device).briefings.get(date.today().isoformat())
    if briefing is None:
        raise HTTPException(status_code=404, detail="no_briefing_today")
    return BriefingResponse(
        brief_date=briefing.brief_date,
        content=briefing.content,
        text=format_morning_text(briefing.content),
        emailed=briefing.emailed,
        created_at=briefing.created_at,
    )


@router.get("/morning", response_model=ComposedReport)
def morning_brief(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> ComposedReport:
    state = request.app.state
    workspace = current_workspace(request, device)
    content = compose_morning_brief(
        workspace.profiles,
        workspace.tasks,
        workspace.prospects,
        workspace.crm,
        workspace.meetings,
        workspace.report_preferences.get(),
        agenda=workspace.agenda,
        inbox=workspace.inbox,
    )
    return ComposedReport(
        brief_date=content["date"], content=content, text=format_morning_text(content)
    )


@router.get("/evening", response_model=ComposedReport)
def evening_report(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> ComposedReport:
    state = request.app.state
    workspace = current_workspace(request, device)
    content = compose_evening_report(
        workspace.profiles,
        workspace.tasks,
        workspace.crm,
        workspace.meetings,
        workspace.report_preferences.get(),
        agenda=workspace.agenda,
    )
    # Storing what was shown keeps the evening e-mail consistent with it.
    workspace.evening_reports.save(content["date"], content)
    return ComposedReport(
        brief_date=content["date"], content=content, text=format_evening_text(content)
    )


@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> PreferencesResponse:
    return _preferences_response(
        current_workspace(request, device).report_preferences.get()
    )


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    payload: SectionPreferences,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> PreferencesResponse:
    preferences = current_workspace(request, device).report_preferences.update(
        morning_sections=payload.morning_sections,
        evening_sections=payload.evening_sections,
    )
    audit("report_preferences_updated", device_id=device.device_id)
    return _preferences_response(preferences)


def _preferences_response(preferences: Any) -> PreferencesResponse:
    return PreferencesResponse(
        morning_sections=list(preferences.morning_sections),
        evening_sections=list(preferences.evening_sections),
        available_morning=[{"key": key, "label": label} for key, label in MORNING_SECTIONS],
        available_evening=[{"key": key, "label": label} for key, label in EVENING_SECTIONS],
    )
