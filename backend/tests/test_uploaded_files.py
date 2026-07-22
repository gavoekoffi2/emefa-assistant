import io

import httpx
import pytest
from docx import Document

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.main import create_app


class ScriptedBrain:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    async def think(self, history, tools):
        self.calls += 1
        if self.actions:
            return AgentStep(action=self.actions.pop(0))
        result = next(item for item in reversed(history) if item.get("role") == "tool")
        content = result["content"]
        if result["name"] == "file_read":
            return AgentStep(answer=f"Lu: {content.get('filename')} => {content.get('text', '')[:80]}")
        return AgentStep(answer=f"Outil exécuté: {result['name']}")


async def _client_for(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_user_can_upload_list_read_and_download_text_file(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "emefa.db"))
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client_for(app) as client:
        unauth = await client.post(
            "/v1/files",
            files={"file": ("note.txt", b"secret", "text/plain")},
        )
        uploaded = await client.post(
            "/v1/files",
            files={"file": ("brief.txt", "Bonjour EMEFA\nAnalyse ce texte".encode(), "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 200
        payload = uploaded.json()
        listed = await client.get("/v1/files", headers=headers)
        read = await client.get(f"/v1/files/{payload['file_id']}", headers=headers)
        download = await client.get(f"/v1/files/{payload['file_id']}/download", headers=headers)

    assert unauth.status_code == 401
    assert payload["filename"] == "brief.txt"
    assert payload["extraction_status"] == "text_extracted"
    assert "Bonjour EMEFA" in payload["text_preview"]
    assert listed.json()[0]["file_id"] == payload["file_id"]
    assert "Analyse ce texte" in read.json()["text"]
    assert download.content == b"Bonjour EMEFA\nAnalyse ce texte"


@pytest.mark.asyncio
async def test_user_can_upload_docx_and_agent_can_read_it(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "emefa.db"))
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client_for(app) as client:
        uploaded = await client.post(
            "/v1/files",
            files={"file": ("contrat.docx", _docx_bytes("Clause importante EMEFA"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=headers,
        )
        assert uploaded.status_code == 200
        file_id = uploaded.json()["file_id"]
        app.state.agent.brain = ScriptedBrain([
            RequestedAction(name="file_read", arguments={"file_id": file_id})
        ])
        run = await client.post(
            "/v1/agent/runs",
            json={"message": "Lis le document envoyé"},
            headers=headers,
        )

    assert uploaded.json()["extraction_status"] == "text_extracted"
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert "Clause importante EMEFA" in run.json()["answer"]


@pytest.mark.asyncio
async def test_user_can_upload_pdf_and_extract_text(tmp_path):
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Texte PDF EMEFA à analyser")
    data = pdf.tobytes()
    app = create_app(Settings(database_path=tmp_path / "emefa.db"))
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client_for(app) as client:
        uploaded = await client.post(
            "/v1/files",
            files={"file": ("analyse.pdf", data, "application/pdf")},
            headers=headers,
        )
        read = await client.get(f"/v1/files/{uploaded.json()['file_id']}", headers=headers)

    assert uploaded.status_code == 200
    assert uploaded.json()["extraction_status"] == "text_extracted"
    assert "Texte PDF EMEFA" in read.json()["text"]


@pytest.mark.asyncio
async def test_uploaded_image_is_stored_with_honest_no_ocr_status(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "emefa.db"))
    token = app.state.devices.enroll("Claude")[1]
    headers = {"Authorization": f"Bearer {token}"}

    async with await _client_for(app) as client:
        uploaded = await client.post(
            "/v1/files",
            files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            headers=headers,
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["extraction_status"] == "image_stored_no_ocr"
