"""Meetings API: capture, review and clean up meeting follow-through."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/meetings", tags=["meetings"])


class ActionPayload(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    owner: str = Field(default="", max_length=120)
    due_date: str | None = Field(default=None, max_length=10)


class MeetingPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    occurred_at: str | None = Field(default=None, max_length=10)
    participants: list[str] = Field(default_factory=list, max_length=40)
    summary: str = Field(default="", max_length=8_000)
    notes: str = Field(default="", max_length=40_000)
    decisions: list[str] = Field(default_factory=list, max_length=40)
    actions: list[ActionPayload] = Field(default_factory=list, max_length=40)
    project: str | None = Field(default=None, max_length=200)
    contact: str | None = Field(default=None, max_length=200)


@router.get("")
def list_meetings(
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
    limit: int = 20,
) -> dict[str, Any]:
    meetings = request.app.state.meetings
    return {
        "meetings": meetings.list(limit=max(1, min(limit, 50))),
        "open_actions": meetings.open_actions(limit=50),
    }


@router.post("", status_code=201)
def capture_meeting(
    payload: MeetingPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    try:
        result = request.app.state.meetings.capture(
            title=payload.title,
            notes=payload.notes,
            occurred_at=payload.occurred_at,
            participants=payload.participants,
            summary=payload.summary,
            decisions=payload.decisions,
            actions=[action.model_dump() for action in payload.actions],
            project=payload.project,
            contact=payload.contact,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit("meeting_captured", device_id=device.device_id, meeting_id=result["meeting_id"])
    return result


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    meeting = request.app.state.meetings.get(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting_not_found")
    return meeting


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(
    meeting_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not request.app.state.meetings.delete(meeting_id):
        raise HTTPException(status_code=404, detail="meeting_not_found")
    audit("meeting_deleted", device_id=device.device_id, meeting_id=meeting_id)
    return Response(status_code=204)
