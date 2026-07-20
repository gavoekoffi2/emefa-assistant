import json

import httpx
import pytest
import pytest_asyncio

from emefa.config import Settings
from emefa.domain.agent import AgentStep, RequestedAction
from emefa.domain.profiles import ProfileRepository
from emefa.infrastructure.deepseek import DeepSeekBrain
from emefa.main import create_app
from emefa.skills import build_tool_shelf


def test_profile_skills_read_and_update(tmp_path):
    profiles = ProfileRepository(tmp_path / "skills.db")
    shelf = build_tool_shelf(profiles)

    read_result = shelf.get("get_profiles").handler({})
    assert read_result["assistant"]["name"] == "EMEFA"

    update_result = shelf.get("update_business_profile").handler(
        {"company_name": "Horizon SARL", "industry": "Transport", "ignored": True}
    )
    assert update_result["updated_fields"] == ["company_name", "industry"]
    assert profiles.get_business().company_name == "Horizon SARL"


def test_tool_descriptions_expose_parameters(tmp_path):
    shelf = build_tool_shelf(ProfileRepository(tmp_path / "desc.db"))
    described = {tool["name"]: tool for tool in shelf.describe()}
    schema = described["update_business_profile"]["parameters"]
    assert schema["type"] == "object"
    assert "offer" in schema["properties"]
    assert described["get_profiles"]["parameters"] is None


@pytest.mark.asyncio
async def test_deepseek_emits_and_replays_tool_calls():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_42",
                                        "type": "function",
                                        "function": {
                                            "name": "update_business_profile",
                                            "arguments": '{"company_name": "Horizon SARL"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "C’est noté pour Horizon SARL."}}]},
        )

    brain = DeepSeekBrain(api_key="k", transport=httpx.MockTransport(handler))
    tools = [
        {
            "name": "update_business_profile",
            "description": "desc",
            "risk": "local_write",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    step = await brain.think([{"role": "user", "content": "Mon entreprise est Horizon SARL"}], tools)
    assert step.action == RequestedAction(
        name="update_business_profile",
        arguments={"company_name": "Horizon SARL"},
        call_id="call_42",
    )
    assert requests[0]["tools"][0]["function"]["name"] == "update_business_profile"

    history = [
        {"role": "user", "content": "Mon entreprise est Horizon SARL"},
        {
            "role": "tool",
            "name": "update_business_profile",
            "call_id": "call_42",
            "arguments": {"company_name": "Horizon SARL"},
            "content": {"updated_fields": ["company_name"]},
        },
    ]
    step = await brain.think(history, tools)
    assert step.answer == "C’est noté pour Horizon SARL."
    replayed = requests[1]["messages"]
    assistant_call = next(m for m in replayed if m.get("tool_calls"))
    tool_reply = next(m for m in replayed if m["role"] == "tool")
    assert assistant_call["tool_calls"][0]["id"] == "call_42"
    assert tool_reply["tool_call_id"] == "call_42"
    assert "updated_fields" in tool_reply["content"]
    await brain.close()


class ScriptedBrain:
    def __init__(self, steps):
        self.steps = list(steps)

    async def think(self, history, tools):
        return self.steps.pop(0)


@pytest_asyncio.fixture
async def client(tmp_path):
    def app_factory(brain):
        return create_app(
            Settings(
                enrollment_code="CODE-SECRET",
                database_path=tmp_path / "agent.db",
                cookie_secure=False,
            ),
            brain=brain,
        )

    yield app_factory


@pytest.mark.asyncio
async def test_agent_run_executes_profile_skill_end_to_end(client, tmp_path):
    brain = ScriptedBrain(
        [
            AgentStep(
                action=RequestedAction(
                    name="update_business_profile",
                    arguments={"company_name": "Horizon SARL"},
                    call_id="call_1",
                )
            ),
            AgentStep(answer="J’ai enregistré Horizon SARL comme entreprise."),
        ]
    )
    app = client(brain)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        response = await web.post("/v1/agent/runs", json={"message": "Mon entreprise est Horizon SARL"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["turns"] == 2
    assert ProfileRepository(tmp_path / "agent.db").get_business().company_name == "Horizon SARL"


def test_update_assistant_profile_skill(tmp_path):
    profiles = ProfileRepository(tmp_path / "assistant.db")
    shelf = build_tool_shelf(profiles)
    result = shelf.get("update_assistant_profile").handler(
        {"interaction_style": "Tutoiement, réponses brèves", "ignored": "x", "name": "  "}
    )
    assert result["updated_fields"] == ["interaction_style"]
    assert profiles.get_assistant().interaction_style == "Tutoiement, réponses brèves"
    assert profiles.get_assistant().name == "EMEFA"
    empty = shelf.get("update_assistant_profile").handler({"name": "   "})
    assert empty["error"] == "no_valid_fields"
