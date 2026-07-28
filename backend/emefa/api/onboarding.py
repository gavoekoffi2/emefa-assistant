"""Welcome-interview API.

The interface only *reflects* the interview: the conversation itself happens
through the ordinary agent endpoints, so there is no second, divergent
onboarding path to maintain.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.observability import audit

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


class TopicRequest(BaseModel):
    topic_id: str = Field(min_length=1, max_length=40)


@router.get("/status")
def status(
    request: Request, _device: Annotated[Device, Depends(current_device)]
) -> dict[str, Any]:
    state = request.app.state.onboarding.status()
    return {**state, "next_question": request.app.state.onboarding.next_question()}


@router.post("/start")
def start(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> dict[str, Any]:
    audit("onboarding_started", device_id=device.device_id)
    return request.app.state.onboarding.start()


@router.post("/skip")
def skip(
    payload: TopicRequest,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    try:
        state = request.app.state.onboarding.skip(payload.topic_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="unknown_topic") from error
    audit("onboarding_topic_skipped", device_id=device.device_id, topic=payload.topic_id)
    return state


@router.post("/resume")
def resume(
    payload: TopicRequest,
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
) -> dict[str, Any]:
    return request.app.state.onboarding.resume(payload.topic_id)


@router.post("/complete")
def complete(
    request: Request, device: Annotated[Device, Depends(current_device)]
) -> dict[str, Any]:
    audit("onboarding_completed", device_id=device.device_id)
    return request.app.state.onboarding.complete()


@router.post("/reopen")
def reopen(
    request: Request, _device: Annotated[Device, Depends(current_device)]
) -> dict[str, Any]:
    """Restart the interview — used from the configuration centre."""
    return request.app.state.onboarding.reopen()
