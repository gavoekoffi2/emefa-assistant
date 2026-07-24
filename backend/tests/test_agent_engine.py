import pytest

from emefa.domain.agent import (
    AgentEngine,
    AgentReply,
    AgentStep,
    AgentTool,
    RequestedAction,
    ToolShelf,
)
from emefa.domain.policy import ActionRisk


class ScriptedBrain:
    def __init__(self, *steps: AgentStep):
        self.steps = list(steps)
        self.calls = 0

    async def think(self, history, tools):
        step = self.steps[self.calls]
        self.calls += 1
        return step


class FailingBrain:
    async def think(self, history, tools):
        raise RuntimeError("provider unavailable")


def failing_tool(_arguments):
    raise RuntimeError("provider secret must never escape")


class RememberingBrain:
    def __init__(self):
        self.histories = []

    async def think(self, history, tools):
        self.histories.append(list(history))
        return AgentStep(answer=f"Réponse {len(self.histories)}")


@pytest.mark.asyncio
async def test_provider_failure_returns_controlled_error():
    result = await AgentEngine(FailingBrain(), ToolShelf()).run("Bonjour")

    assert result == AgentReply(status="failed", error="brain_unavailable", turns=1)


@pytest.mark.asyncio
async def test_tool_failure_returns_controlled_error_instead_of_raising():
    shelf = ToolShelf()
    shelf.add(AgentTool("unstable", "Échoue", ActionRisk.OBSERVE, failing_tool))
    brain = ScriptedBrain(AgentStep(action=RequestedAction(name="unstable")))

    result = await AgentEngine(brain, shelf).run("Exécute")

    assert result.status == "failed"
    assert result.error == "tool_execution_failed"


@pytest.mark.asyncio
async def test_approved_tool_failure_returns_controlled_error_instead_of_raising():
    shelf = ToolShelf()
    shelf.add(AgentTool("unstable", "Échoue", ActionRisk.COMMUNICATE, failing_tool))
    engine = AgentEngine(ScriptedBrain(), shelf)

    result = await engine.execute_approved(RequestedAction(name="unstable"))

    assert result.status == "failed"
    assert result.error == "tool_execution_failed"


@pytest.mark.asyncio
async def test_approved_side_effect_stays_completed_when_final_wording_provider_fails():
    shelf = ToolShelf()
    shelf.add(AgentTool(
        "email_send",
        "Envoie",
        ActionRisk.COMMUNICATE,
        lambda arguments: {"status": "sent", "to": arguments["to"], "subject": arguments["subject"]},
    ))
    engine = AgentEngine(FailingBrain(), shelf)

    result = await engine.execute_approved(RequestedAction(
        name="email_send",
        arguments={"to": "client@example.com", "subject": "Devis", "body": "Bonjour"},
    ))

    assert result.status == "completed"
    assert result.error is None
    assert "client@example.com" in (result.answer or "")
    assert "Devis" in (result.answer or "")


@pytest.mark.asyncio
async def test_direct_answer_completes_in_one_turn():
    engine = AgentEngine(ScriptedBrain(AgentStep(answer="Bonjour Claude")), ToolShelf())

    result = await engine.run("Bonjour")

    assert result == AgentReply(status="completed", answer="Bonjour Claude", turns=1)


@pytest.mark.asyncio
async def test_conversation_keeps_recent_user_and_assistant_turns():
    brain = RememberingBrain()
    engine = AgentEngine(brain, ToolShelf())

    await engine.run("Je m’appelle Claude", conversation_id="browser-1")
    await engine.run("Comment je m’appelle ?", conversation_id="browser-1")

    assert brain.histories[1] == [
        {"role": "user", "content": "Je m’appelle Claude"},
        {"role": "assistant", "content": "Réponse 1"},
        {"role": "user", "content": "Comment je m’appelle ?"},
    ]


@pytest.mark.asyncio
async def test_conversations_are_isolated_by_device():
    brain = RememberingBrain()
    engine = AgentEngine(brain, ToolShelf())

    await engine.run("Secret A", conversation_id="browser-a")
    await engine.run("Bonjour B", conversation_id="browser-b")

    assert brain.histories[1] == [{"role": "user", "content": "Bonjour B"}]


@pytest.mark.asyncio
async def test_observation_tool_runs_then_brain_answers():
    shelf = ToolShelf()
    shelf.add(
        AgentTool(
            name="battery_level",
            description="Lit le niveau de batterie",
            risk=ActionRisk.OBSERVE,
            handler=lambda arguments: {"percent": 82},
        )
    )
    brain = ScriptedBrain(
        AgentStep(action=RequestedAction(name="battery_level", arguments={})),
        AgentStep(answer="La batterie est à 82 %."),
    )

    result = await AgentEngine(brain, shelf).run("Batterie ?")

    assert result.status == "completed"
    assert result.answer == "La batterie est à 82 %."
    assert result.turns == 2


@pytest.mark.asyncio
async def test_communication_waits_without_calling_handler():
    called = False

    def send(arguments):
        nonlocal called
        called = True
        return {"sent": True}

    shelf = ToolShelf()
    shelf.add(AgentTool("send_message", "Envoie un message", ActionRisk.COMMUNICATE, send))
    brain = ScriptedBrain(
        AgentStep(action=RequestedAction(name="send_message", arguments={"text": "Salut"}))
    )

    result = await AgentEngine(brain, shelf).run("Dis salut")

    assert result.status == "confirmation_required"
    assert result.pending_action is not None
    assert result.pending_action.name == "send_message"
    assert called is False


@pytest.mark.asyncio
async def test_money_action_is_blocked():
    shelf = ToolShelf()
    shelf.add(AgentTool("pay", "Effectue un paiement", ActionRisk.MONEY, lambda arguments: None))
    brain = ScriptedBrain(AgentStep(action=RequestedAction(name="pay", arguments={"amount": 5})))

    result = await AgentEngine(brain, shelf).run("Paye")

    assert result.status == "blocked"
    assert result.turns == 1


@pytest.mark.asyncio
async def test_turn_budget_stops_loop():
    shelf = ToolShelf()
    shelf.add(AgentTool("clock", "Lit l'heure", ActionRisk.OBSERVE, lambda arguments: {"time": "10:00"}))
    brain = ScriptedBrain(
        *(AgentStep(action=RequestedAction(name="clock", arguments={})) for _ in range(3))
    )

    result = await AgentEngine(brain, shelf, max_turns=3).run("Boucle")

    assert result.status == "failed"
    assert result.error == "turn_budget_exhausted"
    assert result.turns == 3
