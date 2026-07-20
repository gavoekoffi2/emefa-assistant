"""API for tasks and commitments."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    task_id: str
    title: str
    details: str
    due_date: str | None
    status: str
    bucket: str
    created_at: str


@router.get("", response_model=list[TaskResponse])
def list_open_tasks(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[TaskResponse]:
    return [
        TaskResponse(
            task_id=task.task_id,
            title=task.title,
            details=task.details,
            due_date=task.due_date,
            status=task.status,
            bucket=task.bucket(),
            created_at=task.created_at,
        )
        for task in request.app.state.tasks.list_open()
    ]


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> TaskResponse:
    task = request.app.state.tasks.complete(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found_or_not_open")
    audit("task_completed_via_api", device_id=device.device_id, task_id=task.task_id)
    return TaskResponse(
        task_id=task.task_id,
        title=task.title,
        details=task.details,
        due_date=task.due_date,
        status=task.status,
        bucket=task.bucket(),
        created_at=task.created_at,
    )
