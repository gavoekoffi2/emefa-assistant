import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.tasks import TaskRepository
from emefa.main import create_app


class ScriptedBrain:
    async def think(self, history, tools):
        return AgentStep(answer="Bonjour.")


@pytest.mark.asyncio
async def test_system_status_reports_real_state(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "status.db",
            cookie_secure=False,
        ),
        brain=ScriptedBrain(),
    )
    TaskRepository(tmp_path / "status.db").create("Relancer Horizon")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/system/status")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        response = await web.get("/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["brain_configured"] is True  # explicit brain injected
    assert body["voice_configured"] is False  # no ElevenLabs key in tests
    assert body["open_task_count"] == 1
    assert body["schema_version"] == 6
    skill_names = {skill["name"] for skill in body["skills"]}
    assert {
        "get_profiles",
        "update_business_profile",
        "reset_business_profile",
        "create_task",
        "list_tasks",
        "complete_task",
        "get_daily_brief",
    } <= skill_names
    risks = {skill["name"]: skill["risk"] for skill in body["skills"]}
    assert risks["reset_business_profile"] == "destructive"


@pytest.mark.asyncio
async def test_unconfigured_brain_is_reported_honestly(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "nobrain.db",
            cookie_secure=False,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        body = (await web.get("/v1/system/status")).json()
    assert body["brain_configured"] is False


@pytest.mark.asyncio
async def test_openrouter_key_configures_the_brain(tmp_path):
    from pydantic import SecretStr

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "router.db",
            cookie_secure=False,
            openrouter_api_key=SecretStr("sk-or-test"),
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        body = (await web.get("/v1/system/status")).json()
    assert body["brain_configured"] is True
