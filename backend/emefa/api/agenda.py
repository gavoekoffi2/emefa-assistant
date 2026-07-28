"""Agenda API: the day's schedule, and the preparation before a meeting."""

from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.agenda import EVENT_KINDS, AgendaError
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/agenda", tags=["agenda"])

_KIND_PATTERN = "^(" + "|".join(EVENT_KINDS) + ")$"


class EventPayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    kind: str | None = Field(default=None, pattern=_KIND_PATTERN)
    starts_at: str | None = Field(default=None, max_length=19)
    ends_at: str | None = Field(default=None, max_length=19)
    location: str | None = Field(default=None, max_length=2_000)
    participants: list[str] | None = Field(default=None, max_length=40)
    contact_id: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2_000)


def _guard(action: Any) -> Any:
    try:
        return action()
    except AgendaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("")
def view(
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
    days: int = 7,
) -> dict[str, Any]:
    agenda = request.app.state.agenda
    horizon = max(0, min(days, 60))
    return {
        **agenda.digest(),
        "upcoming": [
            {**asdict(event), "label": event.label()} for event in agenda.upcoming(horizon)
        ],
    }


@router.post("", status_code=201)
def create_event(
    payload: EventPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    event = _guard(lambda: request.app.state.agenda.save_event(None, **fields))
    audit("agenda_event_created", device_id=device.device_id, event_id=event.event_id)
    return {**asdict(event), "label": event.label()}


@router.patch("/{event_id}")
def update_event(
    event_id: str,
    payload: EventPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    event = _guard(lambda: request.app.state.agenda.save_event(event_id, **fields))
    audit("agenda_event_updated", device_id=device.device_id, event_id=event_id)
    return {**asdict(event), "label": event.label()}


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not request.app.state.agenda.delete(event_id):
        raise HTTPException(status_code=404, detail="event_not_found")
    audit("agenda_event_deleted", device_id=device.device_id, event_id=event_id)
    return Response(status_code=204)


@router.get("/{event_id}/preparation")
def preparation(
    event_id: str,
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    try:
        return request.app.state.agenda.prepare(event_id)
    except AgendaError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/day/{when}")
def day(
    when: str,
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    try:
        reference = date.fromisoformat(when)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid_date") from error
    return request.app.state.agenda.digest(reference)
