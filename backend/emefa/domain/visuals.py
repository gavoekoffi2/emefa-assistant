"""Visual cards — what EMEFA shows alongside what she says.

A conversation is the right interface for asking, and the wrong one for
reading a table of twelve rows or comparing six months of sales. A visual card
is the answer to that: EMEFA replies in words, and attaches the thing worth
looking at.

The card is **data, not markup**. The backend decides what to show and hands
over a typed payload; the front end decides how to draw it. Sending HTML would
mean the model composes what the browser renders, and a model that can write
markup into a page can write a script into it.

What EMEFA can actually show is bounded by what this deployment has:

* things the user already gave her — uploaded files, documents she produced;
* things she can compute — a chart from her own figures, a table, a set of
  metrics;
* a location, drawn as coordinates rather than as a street map.

She has no image search and no map tiles, so "affiche-moi la Tour Eiffel"
gets an honest "je ne sais pas aller chercher une image sur le web" rather
than a broken frame. The page's content-security policy would refuse a remote
image anyway; refusing it here means the user is told why.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CardKind(StrEnum):
    #: An image the user uploaded, by file id.
    IMAGE = "image"
    #: A document EMEFA produced, by document id.
    DOCUMENT = "document"
    #: Any other stored file, offered for download.
    FILE = "file"
    #: A bar or line chart computed from EMEFA's own data.
    CHART = "chart"
    #: Rows and columns.
    TABLE = "table"
    #: A point on the globe, with its coordinates. Not a street map.
    MAP = "map"
    #: A short set of named figures — the shape of an analysis result.
    METRICS = "metrics"
    #: A video the user uploaded.
    VIDEO = "video"


class ChartShape(StrEnum):
    BAR = "bar"
    LINE = "line"


MAX_SERIES_POINTS = 60
MAX_TABLE_ROWS = 50
MAX_TABLE_COLUMNS = 8
MAX_METRICS = 8
MAX_TITLE = 120


class VisualCardError(ValueError):
    """The card cannot be built as asked. Raised rather than returning a
    half-formed card, so the caller tells the user instead of rendering an
    empty frame."""


@dataclass(frozen=True, slots=True)
class VisualCard:
    kind: CardKind
    title: str
    #: Kind-specific body. Validated on construction; the front end may trust
    #: its shape.
    payload: dict[str, Any] = field(default_factory=dict)
    #: One line under the title. Where EMEFA says what the user is looking at.
    caption: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "title": self.title,
            "caption": self.caption,
            "payload": self.payload,
        }


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value).split()).strip()[:limit]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # NaN and infinity render as nothing and break axis scaling.
    return number if number == number and abs(number) != float("inf") else None


def image_card(file_id: str, title: str, caption: str = "") -> VisualCard:
    if not file_id:
        raise VisualCardError("file_id required")
    return VisualCard(
        CardKind.IMAGE,
        _clean(title, MAX_TITLE),
        {"file_id": file_id, "url": f"/v1/files/{file_id}/download"},
        _clean(caption, 300),
    )


def video_card(file_id: str, title: str, caption: str = "") -> VisualCard:
    if not file_id:
        raise VisualCardError("file_id required")
    return VisualCard(
        CardKind.VIDEO,
        _clean(title, MAX_TITLE),
        {"file_id": file_id, "url": f"/v1/files/{file_id}/download"},
        _clean(caption, 300),
    )


def document_card(
    document_id: str, title: str, download_url: str = "", caption: str = ""
) -> VisualCard:
    if not document_id:
        raise VisualCardError("document_id required")
    return VisualCard(
        CardKind.DOCUMENT,
        _clean(title, MAX_TITLE),
        {
            "document_id": document_id,
            "url": download_url or f"/v1/documents/{document_id}/download",
        },
        _clean(caption, 300),
    )


def file_card(file_id: str, title: str, content_type: str = "", caption: str = "") -> VisualCard:
    if not file_id:
        raise VisualCardError("file_id required")
    return VisualCard(
        CardKind.FILE,
        _clean(title, MAX_TITLE),
        {
            "file_id": file_id,
            "content_type": content_type,
            "url": f"/v1/files/{file_id}/download",
        },
        _clean(caption, 300),
    )


def chart_card(
    title: str,
    points: list[dict[str, Any]] | list[tuple[str, Any]],
    shape: str = "bar",
    unit: str = "",
    caption: str = "",
) -> VisualCard:
    """A chart from figures EMEFA holds.

    Points with an unreadable value are dropped rather than plotted as zero:
    a missing month drawn as a zero month is a chart that lies.
    """
    cleaned: list[dict[str, Any]] = []
    for point in list(points)[:MAX_SERIES_POINTS]:
        if isinstance(point, dict):
            label, value = point.get("label"), point.get("value")
        else:
            label, value = point[0], point[1] if len(point) > 1 else None
        number = _number(value)
        if number is None or not str(label or "").strip():
            continue
        cleaned.append({"label": _clean(label, 40), "value": number})
    if not cleaned:
        raise VisualCardError("no plottable points")
    try:
        chart_shape = ChartShape(shape.strip().lower())
    except ValueError:
        chart_shape = ChartShape.BAR
    return VisualCard(
        CardKind.CHART,
        _clean(title, MAX_TITLE),
        {"shape": chart_shape.value, "unit": _clean(unit, 20), "points": cleaned},
        _clean(caption, 300),
    )


def table_card(
    title: str,
    columns: list[Any],
    rows: list[list[Any]],
    caption: str = "",
) -> VisualCard:
    headers = [_clean(column, 40) for column in list(columns)[:MAX_TABLE_COLUMNS] if str(column).strip()]
    if not headers:
        raise VisualCardError("columns required")
    body: list[list[str]] = []
    for row in list(rows)[:MAX_TABLE_ROWS]:
        if not isinstance(row, (list, tuple)):
            continue
        # Pad and trim so every row matches the header count: a ragged table
        # renders as a broken grid.
        cells = [_clean(cell, 200) for cell in list(row)[: len(headers)]]
        cells.extend("" for _ in range(len(headers) - len(cells)))
        body.append(cells)
    if not body:
        raise VisualCardError("rows required")
    return VisualCard(
        CardKind.TABLE,
        _clean(title, MAX_TITLE),
        {"columns": headers, "rows": body},
        _clean(caption, 300),
    )


def map_card(
    title: str,
    latitude: Any,
    longitude: Any,
    label: str = "",
    caption: str = "",
) -> VisualCard:
    """A location, as coordinates.

    Deliberately not a street map: no tile provider is configured, and the
    page's content-security policy would refuse remote tiles. What this shows
    is where a place is, not what it looks like — and the caption says so.
    """
    lat, lon = _number(latitude), _number(longitude)
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise VisualCardError("coordinates out of range")
    return VisualCard(
        CardKind.MAP,
        _clean(title, MAX_TITLE),
        {"latitude": lat, "longitude": lon, "label": _clean(label or title, 60)},
        _clean(caption, 300),
    )


def metrics_card(
    title: str, metrics: list[dict[str, Any]], caption: str = ""
) -> VisualCard:
    cleaned = [
        {
            "label": _clean(metric.get("label"), 40),
            "value": _clean(metric.get("value"), 40),
            "hint": _clean(metric.get("hint", ""), 80),
        }
        for metric in list(metrics)[:MAX_METRICS]
        if isinstance(metric, dict) and str(metric.get("label", "")).strip()
    ]
    if not cleaned:
        raise VisualCardError("metrics required")
    return VisualCard(
        CardKind.METRICS, _clean(title, MAX_TITLE), {"metrics": cleaned}, _clean(caption, 300)
    )


# ── collecting cards during a turn ────────────────────────────────────────

#: Cards raised by tools while answering one request.
#:
#: A context variable rather than a field on the tool shelf, because the shelf
#: is shared across concurrent requests and a list on it would hand one user's
#: chart to another. Each request opens its own collector; anything raised
#: outside one is dropped rather than leaking into the next turn.
_collector: ContextVar[list[VisualCard] | None] = ContextVar("visual_cards", default=None)


class CardCollector:
    """Opens a per-request card collector. Use as a context manager."""

    def __init__(self) -> None:
        self.cards: list[VisualCard] = []
        self._token = None

    def __enter__(self) -> CardCollector:
        self._token = _collector.set(self.cards)
        return self

    def __exit__(self, *_exception: object) -> None:
        if self._token is not None:
            _collector.reset(self._token)

    def summaries(self) -> list[dict[str, Any]]:
        return [card.summary() for card in self.cards]


#: A reply carrying eight charts is not an answer, it is a dashboard nobody
#: asked for.
MAX_CARDS_PER_TURN = 3


def offer(card: VisualCard) -> bool:
    """Attach a card to the reply being composed. False when there is no
    collector open, or the turn already has enough."""
    cards = _collector.get()
    if cards is None or len(cards) >= MAX_CARDS_PER_TURN:
        return False
    cards.append(card)
    return True
