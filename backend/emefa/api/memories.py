"""User-facing memory inspection, export, and deletion API."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/memories", tags=["memories"])


class MemoryResponse(BaseModel):
    memory_id: str
    category: str
    content: str
    source: str
    created_at: str


class MemoryCorrection(BaseModel):
    content: str = Field(min_length=3, max_length=500)


@router.get("", response_model=list[MemoryResponse])
def list_memories(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[MemoryResponse]:
    return [
        MemoryResponse(**{
            "memory_id": memory.memory_id,
            "category": memory.category,
            "content": memory.content,
            "source": memory.source,
            "created_at": memory.created_at,
        })
        for memory in request.app.state.memories.list_all()
    ]


@router.get("/export")
def export_memories(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> JSONResponse:
    memories = request.app.state.memories.list_all(limit=10_000)
    audit("memories_exported", device_id=device.device_id, count=len(memories))
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(memories),
        "memories": [
            {
                "memory_id": memory.memory_id,
                "category": memory.category,
                "content": memory.content,
                "source": memory.source,
                "created_at": memory.created_at,
            }
            for memory in memories
        ],
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="emefa-memoire.json"'},
    )


@router.get("/stats")
def memory_stats(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, int]:
    return request.app.state.memories.stats()


@router.get("/search", response_model=list[MemoryResponse])
def search_memories(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    q: Annotated[str, Query(min_length=2, max_length=200)],
) -> list[MemoryResponse]:
    return [
        MemoryResponse(**{
            "memory_id": memory.memory_id,
            "category": memory.category,
            "content": memory.content,
            "source": memory.source,
            "created_at": memory.created_at,
        })
        for memory in request.app.state.memories.search(q)
    ]


@router.get("/{memory_id}/history")
def memory_history(
    memory_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict:
    """Why EMEFA believes this, and what it replaced."""
    history = request.app.state.memories.history(memory_id)
    if history is None:
        raise HTTPException(status_code=404, detail="memory_not_found")
    return history


@router.patch("/{memory_id}", response_model=MemoryResponse)
def correct_memory(
    memory_id: str,
    payload: MemoryCorrection,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> MemoryResponse:
    corrected = request.app.state.memories.correct(memory_id, payload.content)
    if corrected is None:
        raise HTTPException(status_code=404, detail="memory_not_found")
    audit("memory_corrected_via_api", device_id=device.device_id, memory_id=memory_id)
    return MemoryResponse(**{
        "memory_id": corrected.memory_id,
        "category": corrected.category,
        "content": corrected.content,
        "source": corrected.source,
        "created_at": corrected.created_at,
    })


@router.delete("/{memory_id}", status_code=204)
def forget_memory(
    memory_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> None:
    if not request.app.state.memories.forget(memory_id):
        raise HTTPException(status_code=404, detail="memory_not_found")
    audit("memory_forgotten_via_api", device_id=device.device_id, memory_id=memory_id)
