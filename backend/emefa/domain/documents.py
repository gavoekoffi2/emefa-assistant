"""Persistent, path-safe Word document artifacts for EMEFA."""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import UUID, uuid4

from docx import Document
from docx.document import Document as DocxDocument

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentNotFoundError(LookupError):
    pass


class DocumentStore:
    """Store DOCX artifacts under one server-controlled persistent directory."""

    mime_type = _DOCX_MIME

    def __init__(self, database_path: Path) -> None:
        self.root = Path(database_path).parent / "documents"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validated_id(document_id: str) -> str:
        try:
            value = str(UUID(str(document_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise DocumentNotFoundError("document_not_found") from exc
        return value

    def _path(self, document_id: str) -> Path:
        return self.root / f"{self._validated_id(document_id)}.docx"

    @staticmethod
    def _clean_title(title: object) -> str:
        value = str(title).strip()[:180]
        return value or "Document EMEFA"

    @staticmethod
    def _clean_content(content: object) -> str:
        return str(content).strip()[:100_000]

    @staticmethod
    def _build(title: str, content: str) -> DocxDocument:
        document = Document()
        document.add_heading(title, level=0)
        for line in content.splitlines():
            document.add_paragraph(line)
        return document

    def _save(self, document: DocxDocument, destination: Path) -> None:
        temporary = destination.with_suffix(".tmp.docx")
        document.save(str(temporary))
        os.replace(temporary, destination)

    def create(self, title: object, content: object) -> dict[str, str]:
        document_id = str(uuid4())
        clean_title = self._clean_title(title)
        destination = self._path(document_id)
        self._save(self._build(clean_title, self._clean_content(content)), destination)
        return self.describe(document_id)

    def edit(self, document_id: str, title: object | None, content: object) -> dict[str, str]:
        destination = self._path(document_id)
        if not destination.is_file():
            raise DocumentNotFoundError("document_not_found")
        existing = Document(str(destination))
        current_title = existing.paragraphs[0].text if existing.paragraphs else "Document EMEFA"
        clean_title = self._clean_title(current_title if title is None else title)
        self._save(self._build(clean_title, self._clean_content(content)), destination)
        return self.describe(document_id)

    def get(self, document_id: str) -> Path:
        path = self._path(document_id)
        if not path.is_file():
            raise DocumentNotFoundError("document_not_found")
        return path

    def describe(self, document_id: str) -> dict[str, str]:
        path = self.get(document_id)
        document = Document(str(path))
        title = document.paragraphs[0].text if document.paragraphs else "Document EMEFA"
        slug = re.sub(r"[^A-Za-z0-9À-ÿ]+", "-", title).strip("-")[:80] or "document-emefa"
        return {
            "document_id": self._validated_id(document_id),
            "filename": f"{slug}.docx",
            "download_url": f"/v1/documents/{self._validated_id(document_id)}/download",
        }
