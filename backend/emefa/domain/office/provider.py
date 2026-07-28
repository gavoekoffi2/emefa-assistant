"""The office capability boundary.

`CLAUDE.md` §19 asks for exactly this shape:

    Document Capability Interface  →  Provider Adapter  →  renderer

so the renderer can be replaced without touching business logic. What sits
behind it today is a native provider built on python-docx, openpyxl and
python-pptx. What could sit behind it tomorrow is OfficeCLI, a headless
LibreOffice service, or a rendering API — none of which any caller would
notice.

A note on OfficeCLI specifically, since it was named: there is no package by
that name on PyPI, so no adapter is written against something unverified. The
seam is here and a provider is one class away; wiring it up is a change of one
line in the composition root.
"""

from __future__ import annotations

from typing import Protocol

from emefa.domain.office.schemas import (
    BuiltArtifact,
    DeckSpec,
    DocumentSpec,
    WorkbookSpec,
)


class OfficeError(Exception):
    """The artefact could not be produced. Raised rather than returning an
    empty file: a zero-byte quote that downloads successfully is worse than a
    refusal the user can read."""


class OfficeProvider(Protocol):
    """Everything EMEFA needs to produce professional office files.

    Implementations return bytes plus what they computed, never a path: where
    an artefact is stored is the store's business, not the renderer's.
    """

    name: str

    def build_document(self, spec: DocumentSpec) -> BuiltArtifact: ...

    def build_workbook(self, spec: WorkbookSpec) -> BuiltArtifact: ...

    def build_deck(self, spec: DeckSpec) -> BuiltArtifact: ...
