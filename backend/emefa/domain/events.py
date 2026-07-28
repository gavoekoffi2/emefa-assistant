"""In-process event bus.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

Subsystems that must react to each other — memory to conversations, the
proactive engine to budget thresholds, notifications to everything — were
otherwise going to reach into each other directly. That is fine for two of
them and a knot at six.

Deliberately modest: synchronous, in-process, no persistence, no ordering
guarantees beyond subscription order. It exists to decouple, not to be a
message broker. Anything that must survive a restart belongs in a table, not
here.

A failing handler never breaks the publisher. An event is a notification that
something happened; the thing has already happened, and a subscriber's bug is
not a reason to fail the operation that emitted it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeVar

logger = logging.getLogger("emefa.events")


@dataclass(frozen=True, slots=True)
class Event:
    """Base for every event. Subclasses add their own fields."""

    at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass(frozen=True, slots=True)
class ExchangeCompleted(Event):
    conversation_id: str = ""
    source: str = "chat"
    user_text: str = ""
    assistant_text: str = ""


@dataclass(frozen=True, slots=True)
class FactsIngested(Event):
    created: int = 0
    reinforced: int = 0
    superseded: int = 0


@dataclass(frozen=True, slots=True)
class BudgetThresholdReached(Event):
    scope: str = ""
    spent: float = 0.0
    limit: float = 0.0
    ratio: float = 0.0


@dataclass(frozen=True, slots=True)
class InitiativeRaised(Event):
    initiative_id: str = ""
    title: str = ""
    autonomy_level: int = 0
    requires_validation: bool = True


EventType = TypeVar("EventType", bound=Event)
Handler = Callable[[Any], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[EventType], handler: Callable[[EventType], None]) -> None:
        self._handlers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, event_type: type[EventType], handler: Callable[[EventType], None]) -> None:
        if handler in self._handlers[event_type]:  # type: ignore[operator]
            self._handlers[event_type].remove(handler)  # type: ignore[arg-type]

    def publish(self, event: Event) -> int:
        """Deliver to every subscriber of this exact type. Returns how many
        handlers ran, which is what makes the wiring testable."""
        delivered = 0
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
                delivered += 1
            except Exception:
                logger.warning(
                    "event handler failed",
                    extra={"event": type(event).__name__},
                    exc_info=True,
                )
        return delivered
