"""User-facing memory inspection and deletion API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/memories", tags=["memories"])


class MemoryResponse(BaseModel):
    memory_id: str
    category: str
    content: str
    source: str
    created_at: str


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


@router.delete("/{memory_id}", status_code=204)
def forget_memory(
    memory_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> None:
    if not request.app.state.memories.forget(memory_id):
        raise HTTPException(status_code=404, detail="memory_not_found")
    audit("memory_forgotten_via_api", device_id=device.device_id, memory_id=memory_id)
