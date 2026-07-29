"""Command centre — what EMEFA raised on her own, and the user's decision."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/initiatives", tags=["initiatives"])


class CuratorResponse(BaseModel):
    date: str
    text: str
    facts_active: int
    facts_superseded: int
    tokens_today: int
    pricing_configured: bool


@router.get("")
def list_initiatives(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    history: bool = False,
) -> dict[str, Any]:
    repository = request.app.state.proactive_initiatives
    # Expiring on read as well as on the scheduled pass: an initiative whose
    # moment has passed must not still be showing because the loop has not
    # come round yet.
    repository.expire_overdue()
    items = repository.history() if history else repository.open_initiatives()
    return {"initiatives": [item.summary() for item in items], "counts": repository.counts()}


@router.post("/refresh")
def refresh(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    """Run a collection pass now. Same bounded pass the scheduler runs — it
    cannot raise more, or reach further, because a human asked for it."""
    report = request.app.state.proactive.run()
    audit("proactive_refresh", device_id=device.device_id, raised=report.raised)
    return {
        "raised": report.raised,
        "duplicates": report.duplicates,
        "expired": report.expired,
        "skipped_budget": report.skipped_budget,
        "errors": list(report.errors),
    }


@router.post("/{initiative_id}/approve")
def approve(
    initiative_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    initiative = request.app.state.proactive.approve(initiative_id)
    if initiative is None:
        raise HTTPException(status_code=404, detail="initiative_not_found")
    audit("initiative_approved", device_id=device.device_id, initiative_id=initiative_id)
    return initiative.summary()


@router.post("/{initiative_id}/dismiss")
def dismiss(
    initiative_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    initiative = request.app.state.proactive.dismiss(initiative_id)
    if initiative is None:
        raise HTTPException(status_code=404, detail="initiative_not_found")
    audit("initiative_dismissed", device_id=device.device_id, initiative_id=initiative_id)
    return initiative.summary()


@router.get("/curator", response_model=CuratorResponse)
def curator_report(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> CuratorResponse:
    report = request.app.state.curator.run()
    return CuratorResponse(
        date=report.date,
        text=report.as_text(),
        facts_active=report.facts_active,
        facts_superseded=report.facts_superseded,
        tokens_today=report.tokens_today,
        pricing_configured=report.pricing_configured,
    )
