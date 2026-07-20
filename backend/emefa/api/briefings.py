"""Read API for the proactive daily briefing."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.skills import format_brief_text

router = APIRouter(prefix="/v1/briefings", tags=["briefings"])


class BriefingResponse(BaseModel):
    brief_date: str
    content: dict[str, Any]
    text: str
    emailed: bool
    created_at: str


@router.get("/today", response_model=BriefingResponse)
def todays_briefing(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> BriefingResponse:
    briefing = request.app.state.briefings.get(date.today().isoformat())
    if briefing is None:
        raise HTTPException(status_code=404, detail="no_briefing_today")
    return BriefingResponse(
        brief_date=briefing.brief_date,
        content=briefing.content,
        text=format_brief_text(briefing.content),
        emailed=briefing.emailed,
        created_at=briefing.created_at,
    )
