import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.profiles import ProfileRepository
from emefa.infrastructure.deepseek import SYSTEM_PROMPT, DeepSeekBrain
from emefa.main import create_app


@pytest_asyncio.fixture
async def client(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "profiles.db",
            cookie_secure=False,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        await value.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        yield value


def test_default_profiles_are_seeded(tmp_path):
    repository = ProfileRepository(tmp_path / "seeded.db")
    assistant = repository.get_assistant()
    assert assistant.name == "EMEFA"
    assert assistant.primary_language == "fr"
    assert repository.get_business().is_empty()


def test_partial_updates_persist_across_instances(tmp_path):
    ProfileRepository(tmp_path / "p.db").update_business(
        {"company_name": "Horizon SARL", "unknown_field": "ignored"}
    )
    reloaded = ProfileRepository(tmp_path / "p.db").get_business()
    assert reloaded.company_name == "Horizon SARL"
    assert reloaded.offer == ""


def test_system_context_reflects_profiles(tmp_path):
    repository = ProfileRepository(tmp_path / "ctx.db")
    context = repository.system_context()
    assert "EMEFA" in context
    assert "Contexte professionnel" not in context
    repository.update_business({"offer": "Conseil en logistique", "industry": "Transport"})
    repository.update_assistant({"interaction_style": "directe et concise"})
    context = repository.system_context()
    assert "Conseil en logistique" in context
    assert "Transport" in context
    assert "directe et concise" in context


@pytest.mark.asyncio
async def test_profile_endpoints_require_authentication(tmp_path):
    app = create_app(
        Settings(enrollment_code=None, database_path=tmp_path / "anon.db")
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        for path in ("/v1/assistant/profile", "/v1/assistant/business"):
            response = await anonymous.get(path)
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_api_roundtrip(client):
    patched = await client.patch(
        "/v1/assistant/profile",
        json={"name": "EMEFA", "interaction_style": "chaleureuse"},
    )
    assert patched.status_code == 200
    assert patched.json()["interaction_style"] == "chaleureuse"

    business = await client.patch(
        "/v1/assistant/business",
        json={"company_name": "Horizon SARL", "goals": "10 nouveaux clients"},
    )
    assert business.status_code == 200
    fetched = await client.get("/v1/assistant/business")
    assert fetched.json()["company_name"] == "Horizon SARL"
    assert fetched.json()["goals"] == "10 nouveaux clients"


@pytest.mark.asyncio
async def test_deepseek_brain_injects_profile_context():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Bien noté."}}]},
        )

    brain = DeepSeekBrain(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        context_provider=lambda: "Contexte professionnel : Horizon SARL, transport.",
    )
    step = await brain.think([{"role": "user", "content": "Bonjour"}], tools=[])
    assert isinstance(step, AgentStep)
    system_message = captured["messages"][0]
    assert system_message["role"] == "system"
    assert system_message["content"].startswith(SYSTEM_PROMPT.rstrip("\n")[:30])
    assert "Horizon SARL" in system_message["content"]
    await brain.close()
