"""Executive CRM API — the visible side of EMEFA's relational memory.

Everything the assistant records about the business must be inspectable and
correctable by its owner (CLAUDE.md §26), so every entity here is readable,
editable and deletable from the interface, not only from conversation.
"""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.crm import (
    CONTACT_KINDS,
    CONTACT_STATUSES,
    CONTRACT_STATUSES,
    DEAL_STAGES,
    INTERACTION_KINDS,
    PROJECT_HEALTH,
    PROJECT_STATUSES,
    AmbiguousMatchError,
    CrmError,
)
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/crm", tags=["crm"])


def _one_of(values: tuple[str, ...]) -> str:
    """Anchored enum pattern — an unanchored alternation would let
    "clientX" through and only fail later in the domain."""
    return "^(" + "|".join(values) + ")$"

Short = Field(default=None, max_length=200)
Long = Field(default=None, max_length=2_000)
IsoDate = Field(default=None, max_length=10)


class ContactPayload(BaseModel):
    name: str | None = Short
    kind: str | None = Field(default=None, pattern=_one_of(CONTACT_KINDS))
    company: str | None = Short
    role: str | None = Short
    email: str | None = Short
    phone: str | None = Short
    notes: str | None = Long
    status: str | None = Field(default=None, pattern=_one_of(CONTACT_STATUSES))
    follow_up_days: int | None = Field(default=None, ge=0, le=365)


class ProjectPayload(BaseModel):
    name: str | None = Short
    contact_id: str | None = Short
    objective: str | None = Long
    status: str | None = Field(default=None, pattern=_one_of(PROJECT_STATUSES))
    health: str | None = Field(default=None, pattern=_one_of(PROJECT_HEALTH))
    next_step: str | None = Long
    blocker: str | None = Long
    due_date: str | None = IsoDate


class DealPayload(BaseModel):
    title: str | None = Short
    contact_id: str | None = Short
    project_id: str | None = Short
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    stage: str | None = Field(default=None, pattern=_one_of(DEAL_STAGES))
    sent_at: str | None = IsoDate
    response_due_date: str | None = IsoDate
    notes: str | None = Long


class ContractPayload(BaseModel):
    title: str | None = Short
    contact_id: str | None = Short
    project_id: str | None = Short
    start_date: str | None = IsoDate
    end_date: str | None = IsoDate
    value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    status: str | None = Field(default=None, pattern=_one_of(CONTRACT_STATUSES))
    notice_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = Long


class InteractionPayload(BaseModel):
    summary: str = Field(min_length=1, max_length=2_000)
    kind: str = Field(default="note", pattern=_one_of(INTERACTION_KINDS))
    contact_id: str | None = Short
    project_id: str | None = Short
    occurred_at: str | None = IsoDate


def _crm(request: Request, device: Device) -> Any:
    """The caller's own CRM — resolved from their device, never app-wide."""
    return current_workspace(request, device).crm


def _guard(action: Any) -> Any:
    try:
        return action()
    except AmbiguousMatchError as error:
        # 409: the request is well formed, the target is what is undecided.
        raise HTTPException(
            status_code=409,
            detail={"error": str(error), "candidates": error.candidates},
        ) from error
    except CrmError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/overview")
def overview(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> dict[str, Any]:
    """The four executive questions, answered in one payload."""
    return _crm(request, device).overview()


@router.get("/lookup")
def lookup(
    query: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    return _guard(lambda: _crm(request, device).lookup(query))


@router.get("/contacts")
def list_contacts(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    kind: str | None = None,
) -> list[dict[str, Any]]:
    crm = _crm(request, device)
    return [
        {**asdict(contact), "follow_up_due": contact.follow_up_due(),
         "silent_days": contact.silent_days()}
        for contact in crm.list_contacts(kind=kind)
    ]


@router.post("/contacts", status_code=201)
def create_contact(
    payload: ContactPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    contact = _guard(lambda: _crm(request, device).save_contact(None, **fields))
    audit("crm_contact_created", device_id=device.device_id, contact_id=contact.contact_id)
    return asdict(contact)


@router.patch("/contacts/{contact_id}")
def update_contact(
    contact_id: str,
    payload: ContactPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    contact = _guard(lambda: _crm(request, device).save_contact(contact_id, **fields))
    audit("crm_contact_updated", device_id=device.device_id, contact_id=contact_id)
    return asdict(contact)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(
    contact_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not _crm(request, device).delete_contact(contact_id):
        raise HTTPException(status_code=404, detail="contact_not_found")
    audit("crm_contact_deleted", device_id=device.device_id, contact_id=contact_id)
    return Response(status_code=204)


@router.get("/projects")
def list_projects(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    crm = _crm(request, device)
    return [
        {**asdict(project), "blocked": project.is_blocked(), "late": project.is_late()}
        for project in crm.list_projects(include_closed=include_closed)
    ]


@router.post("/projects", status_code=201)
def create_project(
    payload: ProjectPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    project = _guard(lambda: _crm(request, device).save_project(None, **fields))
    audit("crm_project_created", device_id=device.device_id, project_id=project.project_id)
    return asdict(project)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    project = _guard(lambda: _crm(request, device).save_project(project_id, **fields))
    audit("crm_project_updated", device_id=device.device_id, project_id=project_id)
    return asdict(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not _crm(request, device).delete_project(project_id):
        raise HTTPException(status_code=404, detail="project_not_found")
    audit("crm_project_deleted", device_id=device.device_id, project_id=project_id)
    return Response(status_code=204)


@router.get("/deals")
def list_deals(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> list[dict[str, Any]]:
    crm = _crm(request, device)
    return [
        {**asdict(deal), "awaiting_response": deal.awaiting_response()}
        for deal in crm.list_deals()
    ]


@router.post("/deals", status_code=201)
def create_deal(
    payload: DealPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    deal = _guard(lambda: _crm(request, device).save_deal(None, **fields))
    audit("crm_deal_created", device_id=device.device_id, deal_id=deal.deal_id)
    return asdict(deal)


@router.patch("/deals/{deal_id}")
def update_deal(
    deal_id: str,
    payload: DealPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    deal = _guard(lambda: _crm(request, device).save_deal(deal_id, **fields))
    audit("crm_deal_updated", device_id=device.device_id, deal_id=deal_id)
    return asdict(deal)


@router.delete("/deals/{deal_id}", status_code=204)
def delete_deal(
    deal_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not _crm(request, device).delete_deal(deal_id):
        raise HTTPException(status_code=404, detail="deal_not_found")
    audit("crm_deal_deleted", device_id=device.device_id, deal_id=deal_id)
    return Response(status_code=204)


@router.get("/contracts")
def list_contracts(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> list[dict[str, Any]]:
    crm = _crm(request, device)
    return [
        {**asdict(contract), "days_to_expiry": contract.days_to_expiry(),
         "expiring": contract.expiring()}
        for contract in crm.list_contracts()
    ]


@router.post("/contracts", status_code=201)
def create_contract(
    payload: ContractPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    contract = _guard(lambda: _crm(request, device).save_contract(None, **fields))
    audit("crm_contract_created", device_id=device.device_id, contract_id=contract.contract_id)
    return asdict(contract)


@router.patch("/contracts/{contract_id}")
def update_contract(
    contract_id: str,
    payload: ContractPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    contract = _guard(lambda: _crm(request, device).save_contract(contract_id, **fields))
    audit("crm_contract_updated", device_id=device.device_id, contract_id=contract_id)
    return asdict(contract)


@router.delete("/contracts/{contract_id}", status_code=204)
def delete_contract(
    contract_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> Response:
    if not _crm(request, device).delete_contract(contract_id):
        raise HTTPException(status_code=404, detail="contract_not_found")
    audit("crm_contract_deleted", device_id=device.device_id, contract_id=contract_id)
    return Response(status_code=204)


@router.get("/interactions")
def list_interactions(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    contact_id: str | None = None,
    project_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    entries = _crm(request, device).interactions_for(
        contact_id, project_id, limit=max(1, min(limit, 100))
    )
    return [asdict(entry) for entry in entries]


@router.post("/interactions", status_code=201)
def log_interaction(
    payload: InteractionPayload,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    interaction = _guard(
        lambda: _crm(request, device).log_interaction(
            summary=payload.summary,
            kind=payload.kind,
            contact_id=payload.contact_id,
            project_id=payload.project_id,
            occurred_at=payload.occurred_at,
        )
    )
    audit("crm_interaction_logged", device_id=device.device_id)
    return asdict(interaction)
