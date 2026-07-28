"""Signals EMEFA notices on her own.

Every collector here is **deterministic**: it reads EMEFA's own data and
applies a rule. None of them calls a model.

That is a design choice, not a limitation. Proactive work runs unattended, on
a schedule, on the user's money; asking a model "is anything worth mentioning?"
every hour is expensive, non-reproducible, and produces confident nonsense on
a quiet day. A rule that says "this follow-up was due yesterday" is cheap,
always right, and explains itself. Model reasoning belongs *after* the user
engages with an initiative, not in deciding whether to raise one.

A collector returns candidate initiatives. Whether they are raised, deduped,
or dropped is the engine's decision.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone

from emefa.domain.memories import MemoryRepository
from emefa.domain.memory.schemas import FactStatus
from emefa.domain.policy import ActionRisk
from emefa.domain.proactive.schemas import (
    AutonomyLevel,
    Initiative,
    InitiativeType,
)
from emefa.domain.proactive.store import new_initiative_id
from emefa.domain.prospects import ProspectRepository
from emefa.domain.tasks import TaskRepository

#: A prospect untouched for this long is drifting, whatever its stage says.
STALE_PROSPECT_DAYS = 21
#: How long a reminder stays worth showing before it expires itself.
REMINDER_LIFETIME_DAYS = 3

Collector = Callable[[date], list[Initiative]]


def _deadline(today: date, days: int) -> str:
    return datetime.combine(
        today + timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc
    ).isoformat(timespec="seconds")


def overdue_tasks(tasks: TaskRepository) -> Collector:
    """Commitments whose date has passed. The single most useful thing an
    assistant can notice unprompted."""

    def collect(today: date) -> list[Initiative]:
        late = [task for task in tasks.list_open() if task.bucket(today) == "en_retard"]
        if not late:
            return []
        titles = ", ".join(task.title for task in late[:3])
        more = f" (+{len(late) - 3})" if len(late) > 3 else ""
        return [
            Initiative(
                initiative_id=new_initiative_id(),
                type=InitiativeType.ALERT,
                title=f"{len(late)} tâche(s) en retard",
                reason=f"Échéance dépassée : {titles}{more}.",
                next_action="Reprogrammer ou clôturer ces tâches.",
                autonomy_level=AutonomyLevel.SUGGEST,
                risk=ActionRisk.PERSONAL_READ,
                # Keyed on the day, so the alert renews each morning instead of
                # sitting there stale, but never twice in one day.
                dedupe_key=f"overdue-tasks:{today.isoformat()}",
                deadline=_deadline(today, REMINDER_LIFETIME_DAYS),
                payload={"task_ids": [task.task_id for task in late]},
            )
        ]

    return collect


def due_follow_ups(prospects: ProspectRepository) -> Collector:
    """Commercial follow-ups whose date has arrived."""

    def collect(today: date) -> list[Initiative]:
        due = prospects.due_follow_ups(today)
        if not due:
            return []
        names = ", ".join(prospect.name for prospect in due[:3])
        more = f" (+{len(due) - 3})" if len(due) > 3 else ""
        return [
            Initiative(
                initiative_id=new_initiative_id(),
                type=InitiativeType.REMINDER,
                title=f"{len(due)} relance(s) commerciale(s) à faire",
                reason=f"Prochaine action datée à aujourd'hui ou avant : {names}{more}.",
                next_action="Préparer les relances et fixer la prochaine action.",
                # PREPARE, not EXTERNAL_ACTION: EMEFA may write the draft
                # unprompted, never send it.
                autonomy_level=AutonomyLevel.PREPARE,
                risk=ActionRisk.PERSONAL_READ,
                dedupe_key=f"due-follow-ups:{today.isoformat()}",
                deadline=_deadline(today, REMINDER_LIFETIME_DAYS),
                payload={"prospect_ids": [prospect.prospect_id for prospect in due]},
            )
        ]

    return collect


def stale_prospects(prospects: ProspectRepository) -> Collector:
    """Opportunities nobody has touched. These are the ones that quietly die."""

    def collect(today: date) -> list[Initiative]:
        cutoff = (today - timedelta(days=STALE_PROSPECT_DAYS)).isoformat()
        stale = [
            prospect
            for prospect in prospects.list_open()
            if (prospect.updated_at or "")[:10] < cutoff and not prospect.next_action_date
        ]
        if not stale:
            return []
        names = ", ".join(prospect.name for prospect in stale[:3])
        return [
            Initiative(
                initiative_id=new_initiative_id(),
                type=InitiativeType.SUGGESTION,
                title=f"{len(stale)} opportunité(s) sans suite",
                reason=(
                    f"Aucun mouvement depuis plus de {STALE_PROSPECT_DAYS} jours "
                    f"et aucune action prévue : {names}."
                ),
                next_action="Décider : relancer, requalifier ou clore.",
                autonomy_level=AutonomyLevel.SUGGEST,
                risk=ActionRisk.PERSONAL_READ,
                # Weekly: a dormant pipeline is a weekly conversation, not a
                # daily nag.
                dedupe_key=f"stale-prospects:{today.isocalendar().week}",
                deadline=_deadline(today, 7),
                payload={"prospect_ids": [prospect.prospect_id for prospect in stale]},
            )
        ]

    return collect


def memory_changed(memories: MemoryRepository, window_hours: int = 26) -> Collector:
    """Beliefs EMEFA revised on her own.

    When extraction supersedes a fact, EMEFA has quietly changed her mind about
    the user's business. Telling them is not politeness — an assistant that
    silently rewrites what it believes about you is one you cannot correct.
    """

    def collect(today: date) -> list[Initiative]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=window_hours)
        ).isoformat()
        revised = [
            fact
            for fact in memories.kernel.list_facts(FactStatus.SUPERSEDED, limit=20)
            if fact.updated_at >= cutoff
        ]
        if not revised:
            return []
        return [
            Initiative(
                initiative_id=new_initiative_id(),
                type=InitiativeType.REVIEW,
                title=f"{len(revised)} souvenir(s) mis à jour",
                reason=(
                    "J'ai remplacé ce que je croyais savoir : "
                    + " ; ".join(fact.render() for fact in revised[:3])
                ),
                next_action="Vérifier la nouvelle version, corriger si besoin.",
                autonomy_level=AutonomyLevel.SUGGEST,
                risk=ActionRisk.PERSONAL_READ,
                dedupe_key=f"memory-changed:{today.isoformat()}",
                deadline=_deadline(today, REMINDER_LIFETIME_DAYS),
                payload={"fact_ids": [fact.fact_id for fact in revised]},
            )
        ]

    return collect


def default_collectors(
    tasks: TaskRepository,
    prospects: ProspectRepository,
    memories: MemoryRepository,
) -> Sequence[Collector]:
    return (
        overdue_tasks(tasks),
        due_follow_ups(prospects),
        stale_prospects(prospects),
        memory_changed(memories),
    )
