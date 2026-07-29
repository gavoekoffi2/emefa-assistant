import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from emefa.domain.profiles import ProfileRepository
from emefa.domain.uploaded_files import UploadedFileStore
from emefa.infrastructure.vision import OpenRouterVisionAnalyzer
from emefa.main import create_app
from emefa.config import Settings
from emefa.skills import build_tool_shelf


class RecordingVisionAnalyzer:
    def __init__(self):
        self.calls = []

    async def analyze(self, image_path, content_type, question):
        self.calls.append((image_path, content_type, question))
        return "Je vois un document photographié."


@pytest.mark.asyncio
async def test_openrouter_vision_sends_private_image_as_data_url(tmp_path):
    image = tmp_path / "photo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage-test")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request, payload))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Une facture est visible."}}]},
        )

    analyzer = OpenRouterVisionAnalyzer(
        api_key="secret",
        model="google/gemini-2.5-flash-lite",
        transport=httpx.MockTransport(handler),
    )

    result = await analyzer.analyze(image, "image/png", "Que vois-tu ?")

    assert result == "Une facture est visible."
    request, payload = requests[0]
    assert request.url.path == "/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer secret"
    assert payload["model"] == "google/gemini-2.5-flash-lite"
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Que vois-tu ?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
    )
    await analyzer.close()


@pytest.mark.asyncio
async def test_image_analyze_skill_reads_only_uploaded_images(tmp_path):
    database = tmp_path / "emefa.db"
    uploads = UploadedFileStore(database)
    image = uploads.save("photo.png", "image/png", b"\x89PNG\r\n\x1a\nimage-test")
    text = uploads.save("note.txt", "text/plain", b"Bonjour")
    analyzer = RecordingVisionAnalyzer()
    shelf = build_tool_shelf(
        ProfileRepository(database),
        uploaded_files=uploads,
        vision_analyzer=analyzer,
    )

    result = await shelf.get("image_analyze").handler(
        {"file_id": image.file_id, "question": "Lis ce document"}
    )
    rejected = await shelf.get("image_analyze").handler(
        {"file_id": text.file_id, "question": "Lis ceci"}
    )

    assert result == {
        "file_id": image.file_id,
        "filename": "photo.png",
        "analysis": "Je vois un document photographié.",
    }
    assert analyzer.calls[0][1:] == ("image/png", "Lis ce document")
    assert rejected == {"error": "file_is_not_an_image"}
    described = {tool["name"]: tool for tool in shelf.describe()}
    assert described["image_analyze"]["risk"] == "personal_read"
    assert described["image_analyze"]["parameters"]["required"] == ["file_id"]


def test_image_analyze_skill_is_absent_without_vision_provider(tmp_path):
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "emefa.db"),
        uploaded_files=UploadedFileStore(tmp_path / "emefa.db"),
    )

    assert "image_analyze" not in {tool["name"] for tool in shelf.describe()}


def test_openrouter_configuration_activates_vision_tool(tmp_path):
    app = create_app(
        Settings(
            database_path=tmp_path / "emefa.db",
            openrouter_api_key=SecretStr("configured-key"),
        )
    )

    names = {tool["name"] for tool in app.state.agent.tools.describe()}
    assert "image_analyze" in names
    assert app.state.vision.model == "google/gemini-2.5-flash-lite"
