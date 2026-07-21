"""Authenticated download access to EMEFA document artifacts."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from emefa.api.devices import current_device
from emefa.domain.devices import Device
from emefa.domain.documents import DocumentNotFoundError

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("/{document_id}/download", response_class=FileResponse)
def download_document(
    document_id: str,
    request: Request,
    _device: Annotated[Device, Depends(current_device)],
) -> FileResponse:
    try:
        path = request.app.state.documents.get(document_id)
        metadata = request.app.state.documents.describe(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document_not_found") from exc
    return FileResponse(
        path=str(path),
        media_type=request.app.state.documents.mime_type,
        filename=metadata["filename"],
    )
