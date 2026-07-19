import json

import httpx
import pytest

from emefa.infrastructure.deepseek import DeepSeekBrain


@pytest.mark.asyncio
async def test_deepseek_brain_returns_assistant_answer():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer private-test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-chat"
        assert payload["messages"][-1] == {"role": "user", "content": "Bonjour"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Bonjour Claude, comment puis-je vous aider ?"}}]},
        )

    brain = DeepSeekBrain(
        api_key="private-test-key",
        transport=httpx.MockTransport(handler),
    )
    step = await brain.think([{"role": "user", "content": "Bonjour"}], [])

    assert step.answer == "Bonjour Claude, comment puis-je vous aider ?"
    assert step.action is None
    await brain.close()
