"""Visual cards.

Two things are being pinned: a card never carries markup, and a card never
carries a figure nobody supplied.
"""

import asyncio

import httpx
import pytest

from emefa.config import Settings
from emefa.domain import visuals
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.visuals import (
    MAX_CARDS_PER_TURN,
    MAX_TABLE_ROWS,
    CardCollector,
    CardKind,
    VisualCardError,
)
from emefa.main import create_app


def test_a_chart_never_plots_a_value_nobody_gave(tmp_path):
    """A missing month drawn as a zero month is a chart that lies."""
    card = visuals.chart_card(
        "Ventes",
        [
            {"label": "Janvier", "value": 120},
            {"label": "Février", "value": None},
            {"label": "Mars", "value": "pas un nombre"},
            {"label": "", "value": 400},
            {"label": "Avril", "value": 90},
        ],
    )
    assert [point["label"] for point in card.payload["points"]] == ["Janvier", "Avril"]

    with pytest.raises(VisualCardError):
        visuals.chart_card("Vide", [{"label": "Janvier", "value": "?"}])


def test_charts_reject_values_that_break_a_scale():
    with pytest.raises(VisualCardError):
        visuals.chart_card("NaN", [{"label": "A", "value": float("nan")}])
    with pytest.raises(VisualCardError):
        visuals.chart_card("Infini", [{"label": "A", "value": float("inf")}])


def test_tables_are_rectangular_and_bounded():
    card = visuals.table_card(
        "Pipeline",
        ["Client", "Étape", "Montant"],
        [
            ["Horizon", "Devis"],  # short row is padded
            ["Clinique", "Signé", "4 000 000", "colonne en trop"],  # long row is trimmed
            "pas une ligne",
        ],
    )
    rows = card.payload["rows"]
    assert all(len(row) == 3 for row in rows), "a ragged table renders as a broken grid"
    assert rows[0] == ["Horizon", "Devis", ""]
    assert len(rows) == 2

    big = visuals.table_card("Grand", ["A"], [[str(index)] for index in range(200)])
    assert len(big.payload["rows"]) == MAX_TABLE_ROWS

    with pytest.raises(VisualCardError):
        visuals.table_card("Sans colonnes", [], [["a"]])


def test_a_location_refuses_impossible_coordinates():
    card = visuals.map_card("Lomé", 6.1319, 1.2228)
    assert card.kind is CardKind.MAP
    assert card.payload["label"] == "Lomé"

    for latitude, longitude in ((95, 0), (0, 200), ("nord", 0)):
        with pytest.raises(VisualCardError):
            visuals.map_card("Impossible", latitude, longitude)


def test_cards_reference_stored_resources_never_remote_urls():
    """The page's content-security policy refuses remote images. A card that
    tried would render as a broken frame instead of an honest refusal."""
    for card in (
        visuals.image_card("file-1", "Photo"),
        visuals.document_card("doc-1", "Devis"),
        visuals.file_card("file-2", "Archive", "application/zip"),
        visuals.video_card("file-3", "Démo"),
    ):
        assert card.payload["url"].startswith("/v1/")


def test_the_collector_is_per_request():
    """The tool shelf is shared across concurrent requests; a list on it would
    hand one user's chart to another."""
    seen: dict[str, list] = {}

    async def turn(name: str, label: str) -> None:
        with CardCollector() as collector:
            await asyncio.sleep(0)  # force the two turns to interleave
            visuals.offer(visuals.metrics_card(label, [{"label": label, "value": "1"}]))
            await asyncio.sleep(0)
            seen[name] = collector.summaries()

    async def both() -> None:
        await asyncio.gather(turn("a", "Alice"), turn("b", "Bob"))

    asyncio.run(both())

    assert [card["title"] for card in seen["a"]] == ["Alice"]
    assert [card["title"] for card in seen["b"]] == ["Bob"]


def test_a_card_raised_outside_a_turn_is_dropped():
    assert visuals.offer(visuals.metrics_card("Orphelin", [{"label": "x", "value": "1"}])) is False


def test_a_turn_cannot_become_a_dashboard():
    with CardCollector() as collector:
        for index in range(10):
            visuals.offer(
                visuals.metrics_card(f"Carte {index}", [{"label": "x", "value": "1"}])
            )
    assert len(collector.cards) == MAX_CARDS_PER_TURN


# ── through the agent ─────────────────────────────────────────────────────


def build_app(tmp_path, brain=None):
    class Default:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    return create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "visuals.db",
            cookie_secure=False,
        ),
        brain=brain or Default(),
    )


def test_the_tools_refuse_what_does_not_exist(tmp_path):
    app = build_app(tmp_path)
    tools = app.state.agent.tools

    assert tools.get("show_file").handler({"file_id": "absent"})["error"] == "file_not_found"
    assert (
        tools.get("show_document").handler({"document_id": "absent"})["error"]
        == "document_not_found"
    )
    assert tools.get("show_chart").handler({"title": "X"})["error"] == "points_required"
    assert (
        tools.get("show_location").handler(
            {"title": "X", "latitude": 999, "longitude": 0}
        )["error"]
    )


def test_a_created_document_can_be_shown(tmp_path):
    app = build_app(tmp_path)
    tools = app.state.agent.tools
    created = tools.get("document_create").handler(
        {"title": "Proposition Horizon", "content": "Contenu"}
    )
    with CardCollector() as collector:
        result = tools.get("show_document").handler({"document_id": created["document_id"]})
    assert result["shown"] is True
    assert collector.cards[0].kind is CardKind.DOCUMENT
    assert collector.cards[0].title == "Proposition Horizon"


@pytest.mark.asyncio
async def test_cards_reach_the_reply_and_do_not_persist_into_the_next_turn(tmp_path):
    class Brain:
        def __init__(self):
            self.turn = 0

        async def think(self, history, tools):
            self.turn += 1
            # First request: draw a chart, then answer. Second: just answer.
            if self.turn == 1:
                return AgentStep(
                    action=RequestedAction(
                        name="show_chart",
                        arguments={
                            "title": "Ventes",
                            "points": [
                                {"label": "Janvier", "value": 120},
                                {"label": "Février", "value": 180},
                            ],
                        },
                    )
                )
            return AgentStep(answer="Voici l'évolution.")

    app = build_app(tmp_path, Brain())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        first = (await web.post("/v1/agent/runs", json={"message": "Montre les ventes"})).json()
        second = (await web.post("/v1/agent/runs", json={"message": "Merci"})).json()

    assert first["answer"] == "Voici l'évolution."
    assert len(first["cards"]) == 1
    assert first["cards"][0]["kind"] == "chart"
    assert first["cards"][0]["payload"]["points"][1]["value"] == 180
    # A turn with nothing to show clears the previous card rather than leaving
    # a stale chart on screen.
    assert second["cards"] == []


def test_every_card_url_matches_a_route_that_exists(tmp_path):
    """A card pointing at a route nobody serves renders as a broken frame.
    Checked against the app's real routing table rather than against a
    remembered path."""
    app = build_app(tmp_path)
    # The OpenAPI schema rather than app.routes: this FastAPI wraps included
    # routers, so walking app.routes reports the wrappers and not the paths.
    routes = set(app.openapi()["paths"])

    assert "/v1/files/{file_id}/download" in routes
    assert "/v1/documents/{document_id}/download" in routes

    assert visuals.image_card("f", "x").payload["url"] == "/v1/files/f/download"
    assert visuals.video_card("f", "x").payload["url"] == "/v1/files/f/download"
    assert visuals.file_card("f", "x").payload["url"] == "/v1/files/f/download"
    assert visuals.document_card("d", "x").payload["url"] == "/v1/documents/d/download"
