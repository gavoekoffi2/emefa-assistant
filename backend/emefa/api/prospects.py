"""Read API for the local sales pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device

router = APIRouter(prefix="/v1/prospects", tags=["prospects"])


class ProspectResponse(BaseModel):
    prospect_id: str
    name: str
    company: str
    email: str
    phone: str
    stage: str
    notes: str
    next_action: str
    next_action_date: str | None
    follow_up_due: bool
    created_at: str


@router.get("", response_model=list[ProspectResponse])
def list_pipeline(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[ProspectResponse]:
    return [
        ProspectResponse(
            prospect_id=p.prospect_id,
            name=p.name,
            company=p.company,
            email=p.email,
            phone=p.phone,
            stage=p.stage,
            notes=p.notes,
            next_action=p.next_action,
            next_action_date=p.next_action_date,
            follow_up_due=p.follow_up_due(),
            created_at=p.created_at,
        )
        for p in request.app.state.prospects.list_open()
    ]
