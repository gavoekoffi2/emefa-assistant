"""Projects, companies, people — read and write over HTTP."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/entities", tags=["entities"])


class EntityRequest(BaseModel):
    kind: str = Field(default="project", max_length=40)
    name: str = Field(min_length=2, max_length=200)
    scope: str = Field(default="business", max_length=20)
    status: str | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=1_000)
    attributes: dict[str, Any] = Field(default_factory=dict)


class LinkRequest(BaseModel):
    to_entity_id: str = Field(min_length=1, max_length=64)
    relation: str = Field(min_length=1, max_length=40)


class MilestoneRequest(BaseModel):
    milestone: str = Field(min_length=1, max_length=40)
    headline: str = Field(min_length=3, max_length=300)
    occurred_at: str | None = None


@router.get("")
def list_entities(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    kind: Annotated[str | None, Query(max_length=40)] = None,
    scope: Annotated[str | None, Query(max_length=20)] = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
) -> dict[str, Any]:
    found = request.app.state.entities.list_entities(kind=kind, scope=scope, status=status)
    return {
        "entities": [item.summary_dict() for item in found],
        "counts": request.app.state.entities.counts(),
    }


@router.post("", status_code=201)
def create_entity(
    payload: EntityRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    try:
        entity = request.app.state.entities.upsert(
            payload.kind,
            payload.name,
            scope=payload.scope,
            status=payload.status,
            summary=payload.summary,
            attributes=payload.attributes or None,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_name") from None
    audit("entity_upserted", device_id=device.device_id, entity_id=entity.entity_id)
    return entity.summary_dict()


@router.get("/{entity_id}")
def entity_brief(
    entity_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    brief = request.app.state.entity_graph.brief(entity_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    return {**brief.summary(), "text": brief.as_text()}


@router.get("/{entity_id}/story")
def entity_story(
    entity_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    story = request.app.state.timeline.story(entity_id)
    if story is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    return story.summary()


@router.post("/{entity_id}/links", status_code=201)
def link_entity(
    entity_id: str,
    payload: LinkRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    entities = request.app.state.entities
    if entities.get(entity_id) is None or entities.get(payload.to_entity_id) is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    relation = entities.link(entity_id, payload.to_entity_id, payload.relation)
    return {"linked": relation is not None, "already_known": relation is None}


@router.post("/{entity_id}/milestones", status_code=201)
def add_milestone(
    entity_id: str,
    payload: MilestoneRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    entities = request.app.state.entities
    if entities.get(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    entry = entities.record_milestone(
        entity_id, payload.milestone, payload.headline, payload.occurred_at
    )
    audit("entity_milestone_recorded", device_id=device.device_id, entity_id=entity_id)
    return entry.summary()
