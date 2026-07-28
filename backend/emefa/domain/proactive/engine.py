"""The proactive engine and the nightly curator.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

The engine runs collectors, files what they found, and stops. It does not act:
raising an initiative and executing one are separate, and only the second
needs permission. Keeping them apart is what lets EMEFA be attentive without
being dangerous.

Every guarantee CLAUDE.md §34 asks of an autonomous loop is enforced here:
a hard ceiling per pass, a budget check, deadline expiry, deduplication, and
no path from a collector to a tool call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from emefa.domain.budget import BudgetGuard
from emefa.domain.events import EventBus, InitiativeRaised
from emefa.domain.proactive.collectors import Collector
from emefa.domain.proactive.schemas import (
    AutonomyLevel,
    Initiative,
    InitiativeStatus,
    needs_human_validation,
)
from emefa.domain.proactive.store import InitiativeRepository

#: Most initiatives a single pass may raise. Beyond this the user is not being
#: assisted, they are being buried.
MAX_PER_PASS = 5


@dataclass(frozen=True, slots=True)
class ProactiveReport:
    raised: int = 0
    duplicates: int = 0
    expired: int = 0
    skipped_budget: bool = False
    errors: tuple[str, ...] = ()


class ProactiveEngine:
    def __init__(
        self,
        initiatives: InitiativeRepository,
        collectors: Sequence[Collector],
        budget: BudgetGuard | None = None,
        bus: EventBus | None = None,
        max_autonomy: AutonomyLevel = AutonomyLevel.PREPARE,
    ) -> None:
        self.initiatives = initiatives
        self.collectors = collectors
        self.budget = budget
        self.bus = bus
        #: Instance-wide ceiling. An initiative may declare a level above this
        #: and will be clamped down to it — configuration can restrict what
        #: EMEFA does unprompted, never widen it.
        self.max_autonomy = max_autonomy

    def run(self, today: date | None = None) -> ProactiveReport:
        reference = today or date.today()
        expired = self.initiatives.expire_overdue()

        if self.budget is not None and not self.budget.allow("proactive"):
            return ProactiveReport(expired=expired, skipped_budget=True)

        raised = duplicates = 0
        errors: list[str] = []
        for collector in self.collectors:
            try:
                candidates = collector(reference)
            except Exception as error:
                # One broken collector must not silence the others; the user
                # would just see nothing and assume all was well.
                errors.append(type(error).__name__)
                continue
            for candidate in candidates:
                if raised >= MAX_PER_PASS:
                    break
                stored = self.initiatives.raise_initiative(self._clamp(candidate))
                if stored is None:
                    duplicates += 1
                    continue
                raised += 1
                if self.bus is not None:
                    self.bus.publish(
                        InitiativeRaised(
                            initiative_id=stored.initiative_id,
                            title=stored.title,
                            autonomy_level=int(stored.autonomy_level),
                            requires_validation=needs_human_validation(stored),
                        )
                    )
        return ProactiveReport(
            raised=raised,
            duplicates=duplicates,
            expired=expired,
            errors=tuple(errors),
        )

    def _clamp(self, initiative: Initiative) -> Initiative:
        if initiative.autonomy_level <= self.max_autonomy:
            return initiative
        return replace(initiative, autonomy_level=self.max_autonomy)

    # ── user decisions ────────────────────────────────────────────────────

    def approve(self, initiative_id: str) -> Initiative | None:
        return self.initiatives.set_status(initiative_id, InitiativeStatus.APPROVED)

    def dismiss(self, initiative_id: str) -> Initiative | None:
        return self.initiatives.set_status(initiative_id, InitiativeStatus.DISMISSED)

    def complete(self, initiative_id: str) -> Initiative | None:
        return self.initiatives.set_status(initiative_id, InitiativeStatus.COMPLETED)


@dataclass(frozen=True, slots=True)
class CuratorReport:
    """What happened while the user was not looking."""

    date: str
    facts_active: int
    facts_superseded: int
    initiatives: dict[str, int]
    tokens_today: int
    cost_today: float
    pricing_configured: bool
    skills_enabled: list[str]
    memory_events: int

    def as_text(self) -> str:
        lines = [
            f"Entretien du {self.date}",
            "",
            f"Mémoire : {self.facts_active} faits actifs, "
            f"{self.facts_superseded} remplacés, {self.memory_events} évènements.",
            "Initiatives : "
            + (
                ", ".join(f"{status} {count}" for status, count in sorted(self.initiatives.items()))
                or "aucune"
            ),
            f"Compétences activées : {', '.join(self.skills_enabled) or 'aucune'}.",
        ]
        if self.pricing_configured:
            lines.append(f"Consommation : {self.tokens_today} jetons, {self.cost_today:.4f} $.")
        else:
            # Never print a monetary figure that was computed from a price
            # nobody entered.
            lines.append(
                f"Consommation : {self.tokens_today} jetons "
                "(tarif non configuré, coût non calculé)."
            )
        return "\n".join(lines)


class Curator:
    """Nightly maintenance. Reports; never repairs on its own."""

    def __init__(self, memories, initiatives, budget, skills) -> None:
        self.memories = memories
        self.initiatives = initiatives
        self.budget = budget
        self.skills = skills

    def run(self, today: date | None = None) -> CuratorReport:
        reference = (today or date.today()).isoformat()
        stats = self.memories.stats()
        report = self.budget.report()
        return CuratorReport(
            date=reference,
            facts_active=stats["active_facts"],
            facts_superseded=stats["superseded_facts"],
            memory_events=stats["events"],
            initiatives=self.initiatives.counts(),
            tokens_today=int(report["total_tokens"]),
            cost_today=float(report["total_usd"]),
            pricing_configured=bool(report["pricing_configured"]),
            skills_enabled=[manifest.name for manifest in self.skills.active()],
        )
