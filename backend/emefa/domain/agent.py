"""Bounded agent loop for the greenfield EMEFA backend."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from emefa.domain.policy import ActionRisk, Decision, decide

ToolResult = Mapping[str, Any] | None
ToolHandler = Callable[[Mapping[str, Any]], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class RequestedAction:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentStep:
    answer: str | None = None
    action: RequestedAction | None = None

    def __post_init__(self) -> None:
        if (self.answer is None) == (self.action is None):
            raise ValueError("An agent step must contain exactly one answer or action")


@dataclass(frozen=True, slots=True)
class AgentTool:
    name: str
    description: str
    risk: ActionRisk
    handler: ToolHandler
    parameters: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AgentReply:
    status: Literal["completed", "confirmation_required", "blocked", "failed"]
    turns: int
    answer: str | None = None
    pending_action: RequestedAction | None = None
    error: str | None = None


class Brain(Protocol):
    async def think(
        self,
        history: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> AgentStep: ...


class ToolShelf:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def add(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk": tool.risk.value,
                "parameters": dict(tool.parameters) if tool.parameters is not None else None,
            }
            for tool in self._tools.values()
        ]


class ConversationMemory(Protocol):
    def recent(self, conversation_id: str, limit: int = 12) -> list[dict[str, Any]]: ...

    def extend(
        self, conversation_id: str, entries: Sequence[Mapping[str, Any]]
    ) -> None: ...


class InProcessConversationMemory:
    """Fallback memory for tests and store-less setups; lost on restart."""

    def __init__(self) -> None:
        self._conversations: dict[str, list[dict[str, Any]]] = {}

    def recent(self, conversation_id: str, limit: int = 12) -> list[dict[str, Any]]:
        return self._conversations.get(conversation_id, [])[-limit:]

    def extend(self, conversation_id: str, entries: Sequence[Mapping[str, Any]]) -> None:
        bucket = self._conversations.setdefault(conversation_id, [])
        bucket.extend(dict(entry) for entry in entries)


class AgentEngine:
    def __init__(
        self,
        brain: Brain,
        tools: ToolShelf,
        max_turns: int = 4,
        memory: ConversationMemory | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self.brain = brain
        self.tools = tools
        self.max_turns = max_turns
        self.memory = memory or InProcessConversationMemory()

    async def run(self, message: str, conversation_id: str | None = None) -> AgentReply:
        previous = self.memory.recent(conversation_id) if conversation_id else []
        history: list[dict[str, Any]] = [*previous, {"role": "user", "content": message}]
        return await self._advance(history, len(previous), conversation_id)

    async def execute_approved(
        self, action: RequestedAction, conversation_id: str | None = None
    ) -> AgentReply:
        """Execute a user-approved action, then let the brain conclude the turn."""
        tool = self.tools.get(action.name)
        if tool is None:
            return AgentReply(status="failed", error="unknown_tool", turns=0)
        if decide(tool.risk) is Decision.BLOCK:
            return AgentReply(status="blocked", error="risk_blocked", turns=0)
        previous = self.memory.recent(conversation_id) if conversation_id else []
        entry = await self._execute_tool(tool, action)
        history: list[dict[str, Any]] = [*previous, entry]
        return await self._advance(history, len(previous), conversation_id)

    async def _execute_tool(self, tool: AgentTool, action: RequestedAction) -> dict[str, Any]:
        output = tool.handler(action.arguments)
        if inspect.isawaitable(output):
            output = await output
        return {
            "role": "tool",
            "name": tool.name,
            "call_id": action.call_id,
            "arguments": dict(action.arguments),
            "content": dict(output) if output is not None else None,
        }

    def _persist(
        self, conversation_id: str | None, history: list[dict[str, Any]], persisted: int
    ) -> None:
        if conversation_id and len(history) > persisted:
            self.memory.extend(conversation_id, history[persisted:])

    async def _advance(
        self,
        history: list[dict[str, Any]],
        persisted: int,
        conversation_id: str | None,
    ) -> AgentReply:
        for turn in range(1, self.max_turns + 1):
            try:
                step = await self.brain.think(history, self.tools.describe())
            except Exception:
                return AgentReply(status="failed", error="brain_unavailable", turns=turn)
            if step.answer is not None:
                history.append({"role": "assistant", "content": step.answer})
                self._persist(conversation_id, history, persisted)
                return AgentReply(status="completed", answer=step.answer, turns=turn)

            action = step.action
            if action is None:
                return AgentReply(status="failed", error="invalid_brain_step", turns=turn)

            tool = self.tools.get(action.name)
            if tool is None:
                return AgentReply(status="failed", error="unknown_tool", turns=turn)

            decision = decide(tool.risk)
            if decision is Decision.BLOCK:
                return AgentReply(status="blocked", error="risk_blocked", turns=turn)
            if decision is Decision.ASK:
                # Persist the context so the approved action can resume later,
                # even after a restart.
                self._persist(conversation_id, history, persisted)
                return AgentReply(
                    status="confirmation_required",
                    pending_action=action,
                    turns=turn,
                )

            history.append(await self._execute_tool(tool, action))

        return AgentReply(status="failed", error="turn_budget_exhausted", turns=self.max_turns)
