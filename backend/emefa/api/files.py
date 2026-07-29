"""Authenticated upload and access API for user-provided files."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from emefa.api.devices import current_device
from emefa.api.workspace import current_workspace
from emefa.domain.devices import Device
from emefa.domain.uploaded_files import UploadedFileNotFoundError, UploadedFileTooLargeError
from emefa.observability import audit

router = APIRouter(prefix="/v1/files", tags=["files"])


class UploadedFileResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: str
    text_preview: str
    extraction_status: str
    download_url: str


class UploadedFileReadResponse(UploadedFileResponse):
    text: str
    truncated: bool


@router.post("", response_model=UploadedFileResponse)
async def upload_file(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
    file: UploadFile = File(...),
) -> UploadedFileResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")
    try:
        record = current_workspace(request, device).uploaded_files.save(file.filename or "fichier", file.content_type, data)
    except UploadedFileTooLargeError as exc:
        raise HTTPException(status_code=413, detail="file_too_large") from exc
    audit("file_uploaded", file_id=record.file_id, uploaded_filename=record.filename, size_bytes=record.size_bytes)
    return UploadedFileResponse(**asdict(record))


@router.get("", response_model=list[UploadedFileResponse])
def list_files(
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> list[UploadedFileResponse]:
    return [UploadedFileResponse(**asdict(record)) for record in current_workspace(request, device).uploaded_files.list()]


@router.get("/{file_id}", response_model=UploadedFileReadResponse)
def read_file(
    file_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> UploadedFileReadResponse:
    try:
        data = current_workspace(request, device).uploaded_files.read_text(file_id)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="file_not_found") from exc
    return UploadedFileReadResponse(**data)


@router.get("/{file_id}/download", response_class=FileResponse)
def download_file(
    file_id: str,
    request: Request,
    device: Annotated[Device, Depends(current_device)],
) -> FileResponse:
    uploaded_files = current_workspace(request, device).uploaded_files
    try:
        record = uploaded_files.describe(file_id)
        path = uploaded_files.get_path(file_id)
    except UploadedFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="file_not_found") from exc
    return FileResponse(str(path), media_type=record.content_type, filename=record.filename)
