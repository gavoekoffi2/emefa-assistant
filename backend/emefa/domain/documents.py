"""Persistent, path-safe office artifacts (Word, Excel, PowerPoint).

The store owns *persistence and identity* only. Rendering is delegated to an
:class:`~emefa.domain.office.OfficeProvider`, so swapping the office engine
never touches this module or its callers (CLAUDE.md §19).

Every artifact is a real, editable Office file on disk, named by UUID under a
single server-controlled directory, and catalogued in the ``artifacts`` table
so titles survive for formats we cannot cheaply re-read (xlsx/pptx).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from emefa.domain.scope import Ownership, Scope, ScopedStore
from emefa.domain.office.legacy import (
    KIND_EXTENSIONS,
    KIND_MIME_TYPES,
    Block,
    DeckSpec,
    DocumentSpec,
    OfficeProvider,
    PythonOfficeProvider,
    SheetSpec,
    SlideSpec,
    WorkbookSpec,
    blocks_to_text,
    parse_content,
)

_DOCX_MIME = KIND_MIME_TYPES["document"]


class DocumentNotFoundError(LookupError):
    pass


class DocumentStore(ScopedStore):
    """Catalogue of the durable deliverables EMEFA produces.

    Deliverables belong to the **company**. Isolation is enforced twice: the
    catalogue is a scoped table, and each tenant's files live in their own
    directory — so a listing cannot see another company's files even if the
    catalogue were wrong.
    """

    #: Kept for callers that predate multi-format support.
    mime_type = _DOCX_MIME
    ownership = Ownership.TENANT

    def __init__(
        self,
        database_path: Path,
        provider: OfficeProvider | None = None,
        footer: str = "Document préparé par EMEFA",
        scope: Scope | None = None,
    ) -> None:
        super().__init__(database_path, scope)
        self.provider = provider or PythonOfficeProvider()
        self.footer = footer
        self.root = self.database_path.parent / "documents" / self.scope.tenant_id
        self.root.mkdir(parents=True, exist_ok=True)
        self._adopt_legacy_directory()
        self._index_existing_files()

    def for_scope(self, scope: Scope) -> "DocumentStore":
        return DocumentStore(self.database_path, self.provider, self.footer, scope)

    def _adopt_legacy_directory(self) -> None:
        """Move pre-tenant files into the default tenant's directory.

        Before this change every artifact sat directly under ``documents/``.
        Those belong to the deployment that created them — the default tenant —
        and are moved once, on first boot after the upgrade.
        """
        if not self.scope.is_default():
            return
        legacy = self.database_path.parent / "documents"
        for extension in KIND_EXTENSIONS.values():
            for path in legacy.glob(f"*{extension}"):
                if path.parent == self.root:
                    continue
                target = self.root / path.name
                if not target.exists():
                    path.rename(target)

    # -- identity & paths -------------------------------------------------

    @staticmethod
    def _validated_id(document_id: str) -> str:
        try:
            return str(UUID(str(document_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise DocumentNotFoundError("document_not_found") from exc

    def _path(self, document_id: str, kind: str = "document") -> Path:
        extension = KIND_EXTENSIONS.get(kind, ".docx")
        return self.root / f"{self._validated_id(document_id)}{extension}"

    def _locate(self, document_id: str) -> tuple[Path, str]:
        validated = self._validated_id(document_id)
        for kind, extension in KIND_EXTENSIONS.items():
            candidate = self.root / f"{validated}{extension}"
            if candidate.is_file():
                return candidate, kind
        raise DocumentNotFoundError("document_not_found")

    # -- catalogue --------------------------------------------------------

    def _index_existing_files(self) -> None:
        """Adopt artifacts written before the catalogue existed."""
        known = {
            row["artifact_id"] for row in self.fetch_all("artifact_id", "artifacts")
        }
        for kind, extension in KIND_EXTENSIONS.items():
            for path in self.root.glob(f"*{extension}"):
                try:
                    artifact_id = self._validated_id(path.stem)
                except DocumentNotFoundError:
                    continue
                if artifact_id in known:
                    continue
                title = path.stem
                if kind == "document":
                    try:
                        title = self.provider.read_document(path)[0]
                    except Exception:  # a corrupt file must not block boot
                        continue
                self._record(artifact_id, kind, title)

    def _record(self, artifact_id: str, kind: str, title: str) -> None:
        if self.fetch_one("artifact_id", "artifacts", "artifact_id = ?", (artifact_id,)):
            self.update_scoped("artifacts", "artifact_id", artifact_id, {"title": title})
        else:
            self.insert("artifacts", {
                "artifact_id": artifact_id, "kind": kind, "title": title,
            })

    def _title_of(self, artifact_id: str) -> str | None:
        row = self.fetch_one("title", "artifacts", "artifact_id = ?", (artifact_id,))
        return row["title"] if row is not None else None

    # -- cleaning ---------------------------------------------------------

    @staticmethod
    def _clean_title(title: object) -> str:
        return str(title).strip()[:180] or "Document EMEFA"

    @staticmethod
    def _clean_content(content: object) -> str:
        return str(content).strip()[:100_000]

    def _subtitle(self) -> str:
        return datetime.now().strftime("%d/%m/%Y")

    # -- Word -------------------------------------------------------------

    def create(self, title: object, content: object, subtitle: str | None = None) -> dict[str, Any]:
        """Render a professional, fully editable Word document."""
        document_id = str(uuid4())
        clean_title = self._clean_title(title)
        spec = DocumentSpec(
            title=clean_title,
            subtitle=self._subtitle() if subtitle is None else str(subtitle)[:300],
            blocks=parse_content(self._clean_content(content)),
            footer=self.footer,
        )
        self.provider.render_document(spec, self._path(document_id, "document"))
        self._record(document_id, "document", clean_title)
        return self.describe(document_id)

    def edit(self, document_id: str, title: object | None, content: object) -> dict[str, Any]:
        path, kind = self._locate(document_id)
        if kind != "document":
            raise DocumentNotFoundError("document_not_found")
        current_title = self._title_of(self._validated_id(document_id))
        if current_title is None:
            current_title = self.provider.read_document(path)[0]
        clean_title = self._clean_title(current_title if title is None else title)
        spec = DocumentSpec(
            title=clean_title,
            subtitle=self._subtitle(),
            blocks=parse_content(self._clean_content(content)),
            footer=self.footer,
        )
        self.provider.render_document(spec, path)
        self._record(self._validated_id(document_id), "document", clean_title)
        return self.describe(document_id)

    def read(self, document_id: str) -> dict[str, Any]:
        """Return the editable text of a Word artifact, for revisions."""
        path, kind = self._locate(document_id)
        if kind != "document":
            return {**self.describe(document_id), "readable": False}
        title, body = self.provider.read_document(path)
        return {**self.describe(document_id), "readable": True, "title": title, "content": body}

    # -- Excel ------------------------------------------------------------

    def create_workbook(self, title: object, sheets: list[dict[str, Any]]) -> dict[str, Any]:
        """Render a workbook whose formulas stay live for the recipient."""
        workbook_id = str(uuid4())
        clean_title = self._clean_title(title)
        spec = WorkbookSpec(
            title=clean_title,
            sheets=tuple(self._sheet_spec(index, sheet) for index, sheet in enumerate(sheets, 1)),
        )
        self.provider.render_workbook(spec, self._path(workbook_id, "workbook"))
        self._record(workbook_id, "workbook", clean_title)
        return self.describe(workbook_id)

    @staticmethod
    def _sheet_spec(position: int, sheet: dict[str, Any]) -> SheetSpec:
        columns = tuple(str(column)[:120] for column in sheet.get("columns", []) or ())
        rows: list[tuple[Any, ...]] = []
        for row in sheet.get("rows", []) or ():
            cells: list[Any] = []
            for cell in row:
                if isinstance(cell, bool) or cell is None:
                    cells.append("" if cell is None else str(cell))
                elif isinstance(cell, (int, float)):
                    cells.append(cell)
                else:
                    cells.append(str(cell)[:2_000])
            rows.append(tuple(cells))
        return SheetSpec(
            name=str(sheet.get("name") or f"Feuille {position}")[:31],
            columns=columns,
            rows=tuple(rows),
            total_columns=tuple(str(item) for item in sheet.get("total_columns", []) or ()),
            notes=str(sheet.get("notes", ""))[:2_000],
        )

    # -- PowerPoint -------------------------------------------------------

    def create_presentation(
        self, title: object, slides: list[dict[str, Any]], subtitle: str = ""
    ) -> dict[str, Any]:
        deck_id = str(uuid4())
        clean_title = self._clean_title(title)
        spec = DeckSpec(
            title=clean_title,
            subtitle=str(subtitle)[:300] or self._subtitle(),
            slides=tuple(
                SlideSpec(
                    title=str(slide.get("title", ""))[:180] or "Slide",
                    bullets=tuple(
                        str(bullet)[:400] for bullet in (slide.get("bullets") or ())
                    )[:10],
                    notes=str(slide.get("notes", ""))[:2_000],
                )
                for slide in slides
            ),
        )
        self.provider.render_presentation(spec, self._path(deck_id, "presentation"))
        self._record(deck_id, "presentation", clean_title)
        return self.describe(deck_id)

    # -- access -----------------------------------------------------------

    def get(self, document_id: str) -> Path:
        return self._locate(document_id)[0]

    def describe(self, document_id: str) -> dict[str, Any]:
        path, kind = self._locate(document_id)
        artifact_id = self._validated_id(document_id)
        title = self._title_of(artifact_id)
        if title is None:
            title = (
                self.provider.read_document(path)[0] if kind == "document" else artifact_id
            )
        slug = re.sub(r"[^A-Za-z0-9À-ÿ]+", "-", title).strip("-")[:80] or "document-emefa"
        stat = path.stat()
        return {
            "document_id": artifact_id,
            "kind": kind,
            "title": title,
            "filename": f"{slug}{KIND_EXTENSIONS[kind]}",
            "content_type": KIND_MIME_TYPES[kind],
            "size_bytes": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "download_url": f"/v1/documents/{artifact_id}/download",
        }

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        """Newest artifacts first, across all three office formats."""
        candidates: list[Path] = []
        for extension in KIND_EXTENSIONS.values():
            candidates.extend(self.root.glob(f"*{extension}"))
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        records: list[dict[str, Any]] = []
        for path in candidates[: max(1, min(limit, 500))]:
            try:
                records.append(self.describe(path.stem))
            except (DocumentNotFoundError, ValueError, OSError):
                continue
        return records


__all__ = [
    "Block",
    "DocumentNotFoundError",
    "DocumentStore",
    "blocks_to_text",
    "parse_content",
]
