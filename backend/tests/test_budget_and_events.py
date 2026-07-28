"""Usage accounting, spend limits and the event bus."""

import httpx
import pytest

from emefa.config import Settings
from emefa.domain.agent import AgentStep
from emefa.domain.budget import WARN_RATIO, BudgetGuard, UsageTracker
from emefa.domain.events import (
    BudgetThresholdReached,
    EventBus,
    ExchangeCompleted,
    FactsIngested,
)
from emefa.domain.memories import MemoryRepository
from emefa.domain.memory.ingest import ExtractedFact, MemoryIngestor
from emefa.main import create_app


class StubExtractor:
    def __init__(self):
        self.calls = 0

    async def extract(self, transcript):
        self.calls += 1
        return [ExtractedFact("utilisateur", "prefere", "le matin", "preference")]


def test_tokens_are_counted_even_when_no_price_is_configured(tmp_path):
    """A guessed provider price would produce a report the owner acts on and
    that is quietly wrong, so cost stays at zero until they enter theirs."""
    tracker = UsageTracker(tmp_path / "usage.db")
    tracker.record("chat", 1_200, 300, model="deepseek-v4-flash")

    today = tracker.today()
    assert today.total_tokens == 1_500
    assert today.cost_usd == 0.0


def test_cost_is_computed_once_prices_are_set(tmp_path):
    tracker = UsageTracker(tmp_path / "priced.db", price_per_mtok_in=2.0, price_per_mtok_out=8.0)
    tracker.record("chat", 1_000_000, 500_000)
    assert tracker.today().cost_usd == pytest.approx(2.0 + 4.0)


def test_usage_is_split_by_scope(tmp_path):
    tracker = UsageTracker(tmp_path / "scopes.db")
    tracker.record("chat", 100, 100)
    tracker.record("extraction", 700, 200)
    tracker.record("pas-un-scope", 50, 50)  # coerced, never dropped

    assert tracker.today("chat").total_tokens == 300  # the coerced entry lands here
    assert tracker.today("extraction").total_tokens == 900
    assert tracker.today().total_tokens == 1_200


def test_the_guard_warns_before_it_stops(tmp_path):
    tracker = UsageTracker(tmp_path / "guard.db")
    bus = EventBus()
    seen: list[BudgetThresholdReached] = []
    bus.subscribe(BudgetThresholdReached, seen.append)
    guard = BudgetGuard(tracker, {"extraction": 1_000}, bus)

    assert guard.status("extraction").state == "ok"
    assert guard.allow("extraction") is True
    assert seen == []

    tracker.record("extraction", int(1_000 * WARN_RATIO), 0)
    assert guard.status("extraction").state == "warning"
    assert guard.allow("extraction") is True, "a warning must not stop the work"
    assert len(seen) == 1

    # Warned once, not on every call afterwards.
    guard.allow("extraction")
    assert len(seen) == 1

    tracker.record("extraction", 500, 0)
    assert guard.status("extraction").blocked is True
    assert guard.allow("extraction") is False


def test_scopes_without_a_limit_are_unlimited(tmp_path):
    guard = BudgetGuard(UsageTracker(tmp_path / "unlimited.db"), {"extraction": 0})
    assert guard.status("chat").state == "unlimited"
    assert guard.status("extraction").state == "unlimited"
    assert guard.allow("chat") is True


@pytest.mark.asyncio
async def test_an_exhausted_budget_stops_extraction_but_not_the_record(tmp_path):
    """The exchange still reaches the event log, so tomorrow's consolidation
    can pick it up. What the budget stops is the spending."""
    database = tmp_path / "stop.db"
    memories = MemoryRepository(database)
    tracker = UsageTracker(database)
    guard = BudgetGuard(tracker, {"extraction": 100})
    extractor = StubExtractor()
    ingestor = MemoryIngestor(memories, extractor, guard=guard)

    tracker.record("extraction", 200, 0)
    result = await ingestor.ingest(
        "Je préfère systématiquement les réunions le matin, jamais après 17 heures."
    )

    assert result.skipped is True
    assert result.error == "budget_exhausted"
    assert extractor.calls == 0, "the guard must run before the call, not after"
    assert memories.kernel.count_events() == 1


def test_the_bus_delivers_by_type_and_survives_a_failing_handler():
    bus = EventBus()
    received: list[str] = []

    def broken(_event):
        raise RuntimeError("handler bug")

    bus.subscribe(ExchangeCompleted, broken)
    bus.subscribe(ExchangeCompleted, lambda event: received.append(event.user_text))
    bus.subscribe(FactsIngested, lambda event: received.append(f"facts:{event.created}"))

    # The publisher is not punished for a subscriber's bug: the thing being
    # announced has already happened.
    assert bus.publish(ExchangeCompleted(user_text="bonjour")) == 1
    assert bus.publish(FactsIngested(created=3)) == 1
    assert received == ["bonjour", "facts:3"]

    # No subscribers is not an error.
    assert bus.publish(BudgetThresholdReached(scope="chat")) == 0


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received: list[str] = []
    handler = lambda event: received.append(event.user_text)  # noqa: E731
    bus.subscribe(ExchangeCompleted, handler)
    bus.publish(ExchangeCompleted(user_text="un"))
    bus.unsubscribe(ExchangeCompleted, handler)
    bus.publish(ExchangeCompleted(user_text="deux"))
    assert received == ["un"]


@pytest.mark.asyncio
async def test_budget_endpoint_reports_scopes_and_pricing_state(tmp_path):
    class Brain:
        async def think(self, history, tools):
            return AgentStep(answer="Ok.")

    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "api.db",
            cookie_secure=False,
        ),
        brain=Brain(),
    )
    app.state.usage.record("chat", 900, 120)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as web:
        assert (await web.get("/v1/system/budget")).status_code == 401
        await web.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        report = (await web.get("/v1/system/budget")).json()

    assert report["total_tokens"] == 1_020
    assert report["pricing_configured"] is False
    scopes = {item["scope"]: item for item in report["scopes"]}
    assert scopes["chat"]["spent_tokens"] == 1_020
    # Autonomous scopes ship with a ceiling; the user's own chat does not.
    assert scopes["chat"]["state"] == "unlimited"
    assert scopes["extraction"]["limit_tokens"] > 0
