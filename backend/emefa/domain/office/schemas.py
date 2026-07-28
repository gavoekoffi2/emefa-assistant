"""What a professional document *is*, described as data.

An executive assistant does not write "a document". She writes a quote, a set
of minutes, a contract — each with a shape people expect, and each wrong in a
recognisable way when the shape is missing. A quote with no validity date is
not a quote.

So a document is specified, not composed as a string. The specification says
what the thing is and what it contains; the provider decides how to render it
(`CLAUDE.md` §19: capability interface → provider adapter → tool). That
separation is what lets the renderer be swapped — for OfficeCLI, for a
LibreOffice service, for anything better — without touching a single caller.

Nothing here knows about python-docx, openpyxl or PowerPoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class DocumentKind(StrEnum):
    LETTER = "letter"
    CONTRACT = "contract"
    QUOTE = "quote"
    INVOICE = "invoice"
    REPORT = "report"
    MINUTES = "minutes"
    PROPOSAL = "proposal"
    SPECIFICATION = "specification"
    PROCEDURE = "procedure"
    POLICY = "policy"
    MANUAL = "manual"
    CV = "cv"
    MEMO = "memo"
    FORM = "form"


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BULLETS = "bullets"
    NUMBERED = "numbered"
    TABLE = "table"
    #: Label / value pairs — parties to a contract, invoice details.
    FIELDS = "fields"
    #: A ruled space for a name, a date and a signature.
    SIGNATURE = "signature"
    PAGE_BREAK = "page_break"


MAX_BLOCKS = 120
MAX_TABLE_ROWS = 400
MAX_TEXT = 20_000


@dataclass(frozen=True, slots=True)
class Brand:
    """The look a company's documents share.

    Deliberately small. A colour, a name and a footer carry most of what makes
    a document look like it came from a real business; a full brand system is
    a design tool, not an assistant.
    """

    company_name: str = ""
    #: Hex, without the hash. Used for headings and table headers.
    primary_colour: str = "0A617D"
    accent_colour: str = "70ECFF"
    font: str = "Calibri"
    address: str = ""
    contact: str = ""
    footer_note: str = ""


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str = ""
    #: Heading depth, 1–4.
    level: int = 1
    items: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    #: Label/value pairs for FIELDS blocks.
    fields: tuple[tuple[str, str], ...] = ()
    #: Right-align the last table column. Money reads wrong left-aligned.
    numeric_last_column: bool = False


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    kind: DocumentKind
    title: str
    subtitle: str = ""
    #: The user-facing document number — quote reference, invoice number.
    reference: str = ""
    document_date: str = field(default_factory=lambda: date.today().isoformat())
    recipient: str = ""
    blocks: tuple[Block, ...] = ()
    brand: Brand = field(default_factory=Brand)
    #: A table of contents is worth it for a report and absurd on a letter,
    #: so it is a choice rather than a default.
    table_of_contents: bool = False
    page_numbers: bool = True
    header_text: str = ""
    footer_text: str = ""


# ── spreadsheets ──────────────────────────────────────────────────────────


class ColumnFormat(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    MONEY = "money"
    PERCENT = "percent"
    DATE = "date"


class ChartKind(StrEnum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Column:
    header: str
    format: ColumnFormat = ColumnFormat.TEXT
    width: int = 0
    #: A live formula applied down the column, with `{row}` standing in for the
    #: spreadsheet row number: "=C{row}*D{row}". Written as a formula, not as a
    #: computed value, so the sheet stays a spreadsheet and not a screenshot.
    formula: str = ""
    #: Add a total for this column under the last row.
    total: bool = False


@dataclass(frozen=True, slots=True)
class Chart:
    kind: ChartKind = ChartKind.NONE
    title: str = ""
    #: Column headers: one for the labels, one or more for the values.
    label_column: str = ""
    value_columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Sheet:
    name: str
    columns: tuple[Column, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    #: A line above the table, for a period or a note.
    caption: str = ""
    chart: Chart = field(default_factory=Chart)
    freeze_header: bool = True
    autofilter: bool = True


@dataclass(frozen=True, slots=True)
class WorkbookSpec:
    title: str
    sheets: tuple[Sheet, ...] = ()
    brand: Brand = field(default_factory=Brand)


# ── decks ─────────────────────────────────────────────────────────────────


class SlideLayout(StrEnum):
    TITLE = "title"
    SECTION = "section"
    BULLETS = "bullets"
    TABLE = "table"
    CHART = "chart"
    QUOTE = "quote"
    CLOSING = "closing"


@dataclass(frozen=True, slots=True)
class Slide:
    layout: SlideLayout
    title: str = ""
    subtitle: str = ""
    bullets: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    chart: Chart = field(default_factory=Chart)
    #: Chart data when the slide carries its own figures.
    points: tuple[tuple[str, float], ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class DeckSpec:
    title: str
    subtitle: str = ""
    slides: tuple[Slide, ...] = ()
    brand: Brand = field(default_factory=Brand)


@dataclass(frozen=True, slots=True)
class BuiltArtifact:
    """What a provider hands back: bytes plus what the caller must be able to
    state truthfully about them."""

    data: bytes
    extension: str
    #: Figures the provider computed while building — a quote total, a
    #: column sum. Returned so the assistant can quote them without opening
    #: the file, and without inventing them.
    computed: dict[str, float] = field(default_factory=dict)
    #: Things the format could not carry, in the user's terms. Surfaced rather
    #: than silently dropped.
    warnings: tuple[str, ...] = ()
