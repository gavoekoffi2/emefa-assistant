"""User-uploaded file storage and text extraction for EMEFA."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from emefa.domain.scope import DEFAULT_SCOPE, Scope
from uuid import UUID, uuid4

from docx import Document


class UploadedFileNotFoundError(LookupError):
    pass


class UploadedFileTooLargeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UploadedFileRecord:
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: str
    text_preview: str
    extraction_status: str
    download_url: str


_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm", ".log"
}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"
_MAX_TEXT_CHARS = 120_000
_MAX_PREVIEW_CHARS = 1_000
_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadedFileStore:
    """Path-safe persistent storage for arbitrary user files.

    There is no index table here: metadata lives beside each file. Isolation is
    therefore achieved by giving **each tenant its own directory**, so a listing
    physically cannot reach another company's uploads.
    """

    def __init__(
        self,
        database_path: Path,
        max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
        scope: Scope | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.scope = scope or DEFAULT_SCOPE
        self.max_upload_bytes = max_upload_bytes
        self.root = self.database_path.parent / "uploads" / self.scope.tenant_id
        self.root.mkdir(parents=True, exist_ok=True)
        self._adopt_legacy_directory()

    def for_scope(self, scope: Scope) -> "UploadedFileStore":
        return UploadedFileStore(self.database_path, self.max_upload_bytes, scope)

    def _adopt_legacy_directory(self) -> None:
        """Files uploaded before tenants existed belong to the default one."""
        if not self.scope.is_default():
            return
        legacy = self.database_path.parent / "uploads"
        for path in legacy.iterdir() if legacy.is_dir() else ():
            if not path.is_dir() or path == self.root:
                continue
            try:
                UUID(path.name)
            except (ValueError, AttributeError):
                continue  # a tenant directory, not a file directory
            target = self.root / path.name
            if not target.exists():
                path.rename(target)

    @staticmethod
    def _validated_id(file_id: str) -> str:
        try:
            return str(UUID(str(file_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise UploadedFileNotFoundError("file_not_found") from exc

    @staticmethod
    def _safe_filename(filename: str) -> str:
        raw = Path(str(filename or "fichier")).name.strip() or "fichier"
        safe = re.sub(r"[^A-Za-z0-9À-ÿ._ -]+", "-", raw).strip(" .-")[:180]
        return safe or "fichier"

    def _dir(self, file_id: str) -> Path:
        return self.root / self._validated_id(file_id)

    def _metadata_path(self, file_id: str) -> Path:
        return self._dir(file_id) / "metadata.json"

    def _load_metadata(self, file_id: str) -> dict[str, object]:
        path = self._metadata_path(file_id)
        if not path.is_file():
            raise UploadedFileNotFoundError("file_not_found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _content_path(self, file_id: str) -> Path:
        metadata = self._load_metadata(file_id)
        return self._dir(file_id) / str(metadata["stored_filename"])

    def _record_from_metadata(self, metadata: dict[str, object]) -> UploadedFileRecord:
        file_id = str(metadata["file_id"])
        return UploadedFileRecord(
            file_id=file_id,
            filename=str(metadata["filename"]),
            content_type=str(metadata["content_type"]),
            size_bytes=int(str(metadata["size_bytes"])),
            created_at=str(metadata["created_at"]),
            text_preview=str(metadata.get("text_preview", "")),
            extraction_status=str(metadata.get("extraction_status", "stored")),
            download_url=f"/v1/files/{file_id}/download",
        )

    def save(self, filename: str, content_type: str | None, data: bytes) -> UploadedFileRecord:
        if len(data) > self.max_upload_bytes:
            raise UploadedFileTooLargeError("file_too_large")
        file_id = str(uuid4())
        directory = self._dir(file_id)
        directory.mkdir(parents=True, exist_ok=False)
        safe_filename = self._safe_filename(filename)
        detected_type = content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        destination = directory / safe_filename
        destination.write_bytes(data)
        text, status = self._extract_text(destination, detected_type)
        metadata = {
            "file_id": file_id,
            "filename": Path(filename or safe_filename).name or safe_filename,
            "stored_filename": safe_filename,
            "content_type": detected_type,
            "size_bytes": len(data),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "text": text[:_MAX_TEXT_CHARS],
            "text_preview": text[:_MAX_PREVIEW_CHARS],
            "extraction_status": status,
        }
        tmp = directory / "metadata.tmp.json"
        tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, directory / "metadata.json")
        return self._record_from_metadata(metadata)

    def list(self, limit: int = 30) -> list[UploadedFileRecord]:
        records: list[UploadedFileRecord] = []
        for metadata_path in self.root.glob("*/metadata.json"):
            try:
                records.append(self._record_from_metadata(json.loads(metadata_path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                continue
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records[: max(1, min(limit, 100))]

    def describe(self, file_id: str) -> UploadedFileRecord:
        return self._record_from_metadata(self._load_metadata(file_id))

    def get_path(self, file_id: str) -> Path:
        path = self._content_path(file_id)
        if not path.is_file():
            raise UploadedFileNotFoundError("file_not_found")
        return path

    def read_text(self, file_id: str, limit: int = 20_000) -> dict[str, object]:
        metadata = self._load_metadata(file_id)
        text = str(metadata.get("text", ""))
        safe_limit = max(1, min(limit, _MAX_TEXT_CHARS))
        return {
            **asdict(self._record_from_metadata(metadata)),
            "text": text[:safe_limit],
            "truncated": len(text) > safe_limit,
        }

    def _extract_text(self, path: Path, content_type: str) -> tuple[str, str]:
        suffix = path.suffix.lower()
        try:
            if content_type == _DOCX_MIME or suffix == ".docx":
                doc = Document(str(path))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
                return text, "text_extracted" if text.strip() else "no_text_found"
            if content_type == _PDF_MIME or suffix == ".pdf":
                try:
                    import fitz  # PyMuPDF
                except Exception:
                    return "", "pdf_extractor_unavailable"
                doc = fitz.open(str(path))
                parts = [page.get_text("text") for page in doc]
                text = "\n".join(part.strip() for part in parts if part.strip())
                return text, "text_extracted" if text.strip() else "no_text_found"
            if suffix in _TEXT_EXTENSIONS or content_type.startswith("text/"):
                raw = path.read_bytes()[: _MAX_TEXT_CHARS * 4]
                text = raw.decode("utf-8", errors="replace")
                return text, "text_extracted" if text.strip() else "no_text_found"
            if content_type.startswith("image/"):
                return "", "image_stored_no_ocr"
            return "", "stored_no_text_extractor"
        except Exception:
            return "", "extraction_failed"
