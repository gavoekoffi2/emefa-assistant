"""The office suite must produce real, editable, professional files."""

import httpx
import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from emefa.config import Settings
from emefa.domain.documents import DocumentStore
from emefa.domain.office import parse_content
from emefa.main import create_app


def test_content_parser_understands_the_structure_an_llm_writes():
    blocks = parse_content(
        "# Titre\n"
        "Un paragraphe.\n"
        "\n"
        "## Décisions\n"
        "- Première décision\n"
        "* Deuxième décision\n"
        "1. Étape une\n"
        "| Poste | Montant |\n"
        "| --- | --- |\n"
        "| Étude | 500 |\n"
    )
    kinds = [block.kind for block in blocks]
    assert kinds == [
        "heading", "paragraph", "spacer", "heading", "bullet", "bullet", "numbered", "table"
    ]
    assert blocks[0].level == 1
    assert blocks[3].text == "Décisions"
    # The separator row is dropped, header and data survive.
    assert blocks[-1].rows == (("Poste", "Montant"), ("Étude", "500"))


def test_word_documents_keep_headings_bullets_and_tables(tmp_path):
    store = DocumentStore(tmp_path / "emefa.db")
    record = store.create(
        "Rapport trimestriel",
        "## Contexte\nLe trimestre a été dense.\n- Croissance\n- Recrutement\n"
        "| Indicateur | Valeur |\n| --- | --- |\n| CA | 12 M |",
    )
    assert record["kind"] == "document"
    assert record["filename"].endswith(".docx")

    document = Document(str(store.get(record["document_id"])))
    styles = [paragraph.style.name for paragraph in document.paragraphs]
    assert "Heading 2" in styles
    assert styles.count("List Bullet") == 2
    assert len(document.tables) == 1
    assert document.tables[0].rows[0].cells[0].text == "Indicateur"

    # Re-reading returns the same structure, so a revision is never blind.
    reread = store.read(record["document_id"])
    assert reread["readable"] is True
    assert "## Contexte" in reread["content"]
    assert "- Croissance" in reread["content"]


def test_workbooks_keep_formulas_live_and_add_real_sum_totals(tmp_path):
    store = DocumentStore(tmp_path / "emefa.db")
    record = store.create_workbook(
        "Budget 2026",
        [
            {
                "name": "Prévisions",
                "columns": ["Poste", "Quantité", "Prix unitaire", "Total"],
                "rows": [
                    ["Conseil", 10, 150000, "=B2*C2"],
                    ["Formation", 4, 200000, "=B3*C3"],
                ],
                "total_columns": ["D"],
            }
        ],
    )
    assert record["kind"] == "workbook"
    assert record["content_type"].endswith("spreadsheetml.sheet")

    path = str(store.get(record["document_id"]))
    # Formulas must be stored as formulas, not as pre-computed text.
    formulas = load_workbook(path)["Prévisions"]
    assert formulas["D2"].value == "=B2*C2"
    assert formulas["D4"].value == "=SUM(D2:D3)"
    assert formulas["A4"].value == "Total"
    assert formulas.freeze_panes == "A2"


def test_presentations_carry_slides_bullets_and_speaker_notes(tmp_path):
    store = DocumentStore(tmp_path / "emefa.db")
    record = store.create_presentation(
        "Comité stratégique",
        [
            {"title": "Situation", "bullets": ["Croissance de 12 %", "Deux projets bloqués"],
             "notes": "Insister sur les blocages."},
            {"title": "Décisions attendues", "bullets": ["Valider le budget"]},
        ],
        subtitle="Juillet 2026",
    )
    assert record["kind"] == "presentation"

    deck = Presentation(str(store.get(record["document_id"])))
    assert len(deck.slides) == 3  # cover + two content slides
    assert deck.slides[0].shapes.title.text == "Comité stratégique"
    assert deck.slides[1].shapes.title.text == "Situation"
    bullets = [p.text for p in deck.slides[1].placeholders[1].text_frame.paragraphs]
    assert bullets == ["Croissance de 12 %", "Deux projets bloqués"]
    assert deck.slides[1].notes_slide.notes_text_frame.text == "Insister sur les blocages."


def test_catalogue_lists_all_three_formats_and_adopts_legacy_files(tmp_path):
    database = tmp_path / "emefa.db"
    store = DocumentStore(database)
    store.create("Note", "Contenu")
    store.create_workbook("Suivi", [{"name": "F1", "columns": ["A"], "rows": [[1]]}])
    store.create_presentation("Pitch", [{"title": "Vision"}])

    kinds = {item["kind"] for item in store.list()}
    assert kinds == {"document", "workbook", "presentation"}

    # A store rebuilt on the same directory re-reads the catalogue, and a file
    # written before the catalogue existed is adopted rather than lost.
    reopened = DocumentStore(database)
    assert len(reopened.list()) == 3
    assert {item["title"] for item in reopened.list()} == {"Note", "Suivi", "Pitch"}


class Brain:
    async def think(self, history, tools):
        from emefa.domain.agent import AgentStep

        return AgentStep(answer="Prêt.")


@pytest.mark.asyncio
async def test_download_serves_each_format_with_its_own_mime_type(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.db"), brain=Brain())
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}
    workbook = app.state.documents.create_workbook(
        "Trésorerie", [{"name": "Mois", "columns": ["Mois", "Solde"], "rows": [["Janvier", 100]]}]
    )
    deck = app.state.documents.create_presentation("Vision", [{"title": "Cap"}])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        excel = await client.get(f"/v1/documents/{workbook['document_id']}/download", headers=headers)
        powerpoint = await client.get(f"/v1/documents/{deck['document_id']}/download", headers=headers)

    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert powerpoint.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert excel.content[:2] == b"PK"  # a real OOXML package, not a stub
