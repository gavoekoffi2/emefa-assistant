"""Usage accounting and spend limits.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

EMEFA had no idea what she cost. `CLAUDE.md` §15 requires tracking tokens,
calls and background jobs, and §34 requires every autonomous loop to carry a
budget limit — neither is possible without a meter.

**Tokens are always recorded. Money only when a price is configured.**
Provider prices change, differ per region and per contract, and are not
something to hard-code from memory: a fabricated price produces a spend report
the owner would act on and that is quietly wrong. So `EMEFA_PRICE_PER_MTOK_IN`
and `EMEFA_PRICE_PER_MTOK_OUT` default to zero, cost stays at zero until the
owner sets their real prices, and the token counters work regardless.

Scopes separate what the user asked for from what EMEFA decided to do:
`chat` and `voice` are the user's; `extraction`, `consolidation` and
`proactive` are EMEFA's own initiative, and it is those that need a ceiling.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from emefa.domain import storage
from emefa.domain.scope import Ownership, Scope, ScopedStore
from emefa.domain.events import BudgetThresholdReached, EventBus

SCOPES = ("chat", "voice", "extraction", "consolidation", "proactive", "mission")

#: Fraction of a limit at which the owner is warned rather than stopped.
WARN_RATIO = 0.8


@dataclass(frozen=True, slots=True)
class Usage:
    scope: str
    input_tokens: int
    output_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    scope: str
    spent_tokens: int
    spent_usd: float
    limit_tokens: int
    #: `ok`, `warning` or `exhausted`. `unlimited` when no limit is set.
    state: str

    @property
    def blocked(self) -> bool:
        return self.state == "exhausted"


class UsageTracker(ScopedStore):
    ownership = Ownership.USER

    def __init__(
        self,
        database_path: Path,
        price_per_mtok_in: float = 0.0,
        price_per_mtok_out: float = 0.0,
        scope: Scope | None = None,
    ) -> None:
        super().__init__(database_path, scope)
        self.price_per_mtok_in = price_per_mtok_in
        self.price_per_mtok_out = price_per_mtok_out

    def for_scope(self, scope: Scope) -> "UsageTracker":
        return type(self)(
            self.database_path, self.price_per_mtok_in, self.price_per_mtok_out, scope
        )

    def _connect(self) -> sqlite3.Connection:
        return storage.connect(self.database_path)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.price_per_mtok_in
            + output_tokens * self.price_per_mtok_out
        ) / 1_000_000

    def record(
        self,
        scope: str,
        input_tokens: int,
        output_tokens: int,
        provider: str = "",
        model: str = "",
    ) -> Usage:
        scope = scope if scope in SCOPES else "chat"
        input_tokens = max(0, int(input_tokens))
        output_tokens = max(0, int(output_tokens))
        cost = self.cost(input_tokens, output_tokens)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO usage_entries (entry_id, tenant_id, user_id, scope, provider, model, "
                "input_tokens, output_tokens, cost_usd, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"use_{uuid.uuid4().hex[:12]}",
                    self.scope.tenant_id,
                    self.scope.user_id,
                    scope,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    cost,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        return Usage(scope, input_tokens, output_tokens, cost)

    def since(self, day: str, scope: str | None = None) -> Usage:
        query = (
            "SELECT COALESCE(SUM(input_tokens), 0) AS i, "
            "COALESCE(SUM(output_tokens), 0) AS o, "
            "COALESCE(SUM(cost_usd), 0) AS c FROM usage_entries "
            "WHERE tenant_id = ? AND user_id = ? AND created_at >= ?"
        )
        parameters: list[object] = [self.scope.tenant_id, self.scope.user_id, day]
        if scope is not None:
            query += " AND scope = ?"
            parameters.append(scope)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return Usage(scope or "all", int(row["i"]), int(row["o"]), float(row["c"]))

    def today(self, scope: str | None = None) -> Usage:
        return self.since(date.today().isoformat(), scope)


class BudgetGuard:
    """Daily token ceilings per scope.

    Limits are expressed in tokens rather than money precisely because tokens
    are the number EMEFA can actually measure without being told a price.
    """

    def __init__(
        self,
        tracker: UsageTracker,
        limits: dict[str, int] | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.tracker = tracker
        self.limits = {scope: limit for scope, limit in (limits or {}).items() if limit > 0}
        self.bus = bus
        self._warned: set[str] = set()

    def status(self, scope: str) -> BudgetStatus:
        usage = self.tracker.today(scope)
        limit = self.limits.get(scope, 0)
        if limit <= 0:
            state = "unlimited"
        elif usage.total_tokens >= limit:
            state = "exhausted"
        elif usage.total_tokens >= limit * WARN_RATIO:
            state = "warning"
        else:
            state = "ok"
        return BudgetStatus(
            scope=scope,
            spent_tokens=usage.total_tokens,
            spent_usd=round(usage.cost_usd, 6),
            limit_tokens=limit,
            state=state,
        )

    def allow(self, scope: str) -> bool:
        """Whether autonomous work in this scope may start.

        Checked before the call, not after: a limit that only notices it was
        crossed once the money is spent is a report, not a budget. The day's
        first warning crossing publishes an event so the owner hears about it
        once rather than on every call.
        """
        status = self.status(scope)
        if status.state in {"warning", "exhausted"} and scope not in self._warned:
            self._warned.add(scope)
            if self.bus is not None:
                self.bus.publish(
                    BudgetThresholdReached(
                        scope=scope,
                        spent=float(status.spent_tokens),
                        limit=float(status.limit_tokens),
                        ratio=(
                            status.spent_tokens / status.limit_tokens
                            if status.limit_tokens
                            else 0.0
                        ),
                    )
                )
        return not status.blocked

    def report(self) -> dict[str, object]:
        today = self.tracker.today()
        return {
            "date": date.today().isoformat(),
            "total_tokens": today.total_tokens,
            "total_usd": round(today.cost_usd, 6),
            #: True when no price is configured, so the UI can say "coût non
            #: configuré" rather than showing a confident 0.00 $.
            "pricing_configured": bool(
                self.tracker.price_per_mtok_in or self.tracker.price_per_mtok_out
            ),
            "scopes": [
                {
                    "scope": scope,
                    "spent_tokens": status.spent_tokens,
                    "spent_usd": status.spent_usd,
                    "limit_tokens": status.limit_tokens,
                    "state": status.state,
                }
                for scope in SCOPES
                for status in [self.status(scope)]
            ],
        }
