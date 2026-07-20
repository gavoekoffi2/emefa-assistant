import httpx
import pytest
from pydantic import SecretStr

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.memories import MemoryRepository
from emefa.domain.policy import ActionRisk
from emefa.domain.profiles import ProfileRepository
from emefa.main import create_app
from emefa.skills import build_tool_shelf


def test_repository_remember_list_forget_and_bounds(tmp_path):
    repository = MemoryRepository(tmp_path / "mem.db")
    saved = repository.remember("  Le client   préfère les appels le matin  ", "preference")
    assert saved.content == "Le client préfère les appels le matin"
    assert saved.category == "preference"
    unknown_category = repository.remember("Autre chose", "invalide")
    assert unknown_category.category == "other"
    assert len(repository.list_all()) == 2
    assert repository.forget(saved.memory_id) is True
    assert repository.forget(saved.memory_id) is False
    with pytest.raises(ValueError):
        repository.remember("   ")


def test_context_block_is_bounded_and_empty_when_no_memory(tmp_path):
    repository = MemoryRepository(tmp_path / "ctx.db")
    assert repository.context_block() == ""
    for index in range(20):
        repository.remember(f"Souvenir numéro {index} " + "x" * 400)
    block = repository.context_block(max_items=12, max_chars=200)
    lines = block.splitlines()
    assert lines[0].startswith("Mémoire durable")
    assert len(lines) == 13  # header + 12 entries max
    assert all(len(line) <= 220 for line in lines)


def test_memory_skills_and_risk_levels(tmp_path):
    memories = MemoryRepository(tmp_path / "skills.db")
    shelf = build_tool_shelf(
        ProfileRepository(tmp_path / "skills.db"), memories=memories
    )
    assert shelf.get("forget_memory").risk is ActionRisk.DESTRUCTIVE
    saved = shelf.get("remember").handler(
        {"content": "Le fournisseur livre le mardi", "category": "fact"}
    )
    memory_id = saved["memory"]["memory_id"]
    listing = shelf.get("list_memories").handler({})
    assert listing["count"] == 1
    assert shelf.get("remember").handler({"content": "ab"})["error"] == "content_too_short"
    assert shelf.get("forget_memory").handler({"memory_id": "absent"})["error"] == "memory_not_found"
    assert shelf.get("forget_memory").handler({"memory_id": memory_id}) == {
        "forgotten": memory_id
    }
    assert memories.list_all() == []


@pytest.mark.asyncio
async def test_memory_api_and_context_composition(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Bonjour.")

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    ProfileRepository(tmp_path / "api.db").update_business({"company_name": "Horizon SARL"})
    repository = MemoryRepository(tmp_path / "api.db")
    memory = repository.remember("Le comptable s'appelle Ama", "relationship")

    context = app.state.compose_context()
    assert "Horizon SARL" in context
    assert "Le comptable s'appelle Ama" in context

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/memories")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        listing = await web.get("/v1/memories")
        assert listing.status_code == 200
        assert listing.json()[0]["content"] == "Le comptable s'appelle Ama"
        deleted = await web.delete(f"/v1/memories/{memory.memory_id}")
        assert deleted.status_code == 204
        assert (await web.delete(f"/v1/memories/{memory.memory_id}")).status_code == 404
        assert (await web.get("/v1/memories")).json() == []
    assert "Le comptable" not in app.state.compose_context()


@pytest.mark.asyncio
async def test_voice_bridge_context_includes_memories(tmp_path):
    import json as jsonlib

    from emefa.infrastructure.voice_llm import VoiceLLMProxy

    seen: list[dict] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(jsonlib.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Oui."}}]})

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "voice.db",
            cookie_secure=False,
            openrouter_api_key=SecretStr("sk-or-test"),
            voice_llm_token=SecretStr("voice-secret"),
        )
    )
    MemoryRepository(tmp_path / "voice.db").remember("Livraison le mardi")
    app.state.voice_llm = VoiceLLMProxy(
        api_key="sk-or-test",
        model="m",
        base_url="https://upstream.test/v1",
        context_provider=app.state.compose_context,
        transport=httpx.MockTransport(upstream),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        response = await web.post(
            "/v1/voice-llm/chat/completions",
            json={"messages": [{"role": "user", "content": "Quand livre-t-on ?"}]},
            headers={"Authorization": "Bearer voice-secret"},
        )
    assert response.status_code == 200
    assert "Livraison le mardi" in seen[0]["messages"][0]["content"]
