"""Telling the story of a client.

"Résume toute l'histoire de ce client" is a different question from "où en
est-on". It wants the arc: when it started, what happened in what order, where
it stands, and how long each stage took.

The story is assembled, never generated. Every sentence traces to a recorded
milestone, so nothing in it can be invented — and where the record is thin,
the story says so instead of filling the gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from emefa.domain.entities.graph import EntityGraph, next_expected
from emefa.domain.entities.schemas import (
    KIND_LABELS,
    MILESTONE_LABELS,
    MILESTONE_ORDER,
    Entity,
    Milestone,
    TimelineEntry,
)

_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _french_date(timestamp: str) -> str:
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp[:10]
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


def _days_between(first: str, second: str) -> int | None:
    try:
        start = datetime.fromisoformat(first)
        end = datetime.fromisoformat(second)
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, (end - start).days)


@dataclass(frozen=True, slots=True)
class Story:
    entity: Entity
    entries: tuple[TimelineEntry, ...]
    #: Milestones from the standard arc that were never recorded. Named
    #: explicitly, because a gap in a history is itself information: a client
    #: with a signature and no delivery is a client to call.
    missing: tuple[str, ...]
    next_expected: str
    duration_days: int | None

    def summary(self) -> dict[str, Any]:
        return {
            **self.entity.summary_dict(),
            "entries": [entry.summary() for entry in self.entries],
            "missing_milestones": list(self.missing),
            "next_expected": self.next_expected,
            "duration_days": self.duration_days,
            "text": self.as_text(),
        }

    def as_text(self) -> str:
        label = KIND_LABELS.get(self.entity.kind, self.entity.kind.value)
        if not self.entries:
            return (
                f"{label} {self.entity.name} : aucun évènement n'a encore été "
                "enregistré. Racontez-moi ce qui s'est passé et je tiens l'historique."
            )

        lines = [f"Histoire — {label} {self.entity.name}", ""]
        previous: TimelineEntry | None = None
        for entry in self.entries:
            gap = ""
            if previous is not None:
                days = _days_between(previous.occurred_at, entry.occurred_at)
                if days is not None and days >= 7:
                    gap = f" (après {days} jours)"
            lines.append(
                f"{_french_date(entry.occurred_at)} — "
                f"{MILESTONE_LABELS.get(entry.milestone, entry.milestone.value)} : "
                f"{entry.headline}{gap}"
            )
            previous = entry

        lines.append("")
        if self.duration_days is not None:
            lines.append(f"Durée totale de la relation : {self.duration_days} jours.")
        if self.missing:
            lines.append("Jamais enregistré : " + ", ".join(self.missing) + ".")
        if self.next_expected:
            lines.append(f"Étape suivante attendue : {self.next_expected}.")
        return "\n".join(lines)


class TimelineBuilder:
    def __init__(self, graph: EntityGraph) -> None:
        self.graph = graph

    def story(self, entity_id: str, include_related: bool = True) -> Story | None:
        entity = self.graph.entities.get(entity_id)
        if entity is None:
            return None

        entries = list(self.graph.entities.timeline(entity_id))

        # A client's story includes what happened on their projects and their
        # invoices: the user thinks of it as one history, not five.
        if include_related:
            for _relation, other, _direction in self.graph.entities.relations_of(entity_id):
                entries.extend(self.graph.entities.timeline(other.entity_id))
        entries.sort(key=lambda entry: (entry.occurred_at, entry.entry_id))

        reached = {entry.milestone for entry in entries}
        missing = tuple(
            MILESTONE_LABELS[milestone]
            for milestone in MILESTONE_ORDER
            if milestone not in reached
        )
        duration = (
            _days_between(entries[0].occurred_at, entries[-1].occurred_at)
            if len(entries) > 1
            else None
        )
        return Story(
            entity=entity,
            entries=tuple(entries),
            missing=missing,
            next_expected=next_expected(entries),
            duration_days=duration,
        )

    def story_by_name(self, name: str, kind: str | None = None) -> Story | None:
        entity = self.graph.entities.resolve(name, kind)
        return self.story(entity.entity_id) if entity is not None else None


#: Milestones EMEFA can infer from something she did herself, so the timeline
#: builds up without the user narrating it. Kept small and literal: guessing
#: that a document is a proposal because it has "proposition" in the title is
#: acceptable; guessing that a client is negotiating is not.
DERIVED_MILESTONES: dict[str, Milestone] = {
    "document_create": Milestone.PROPOSAL,
    "create_task": Milestone.FOLLOW_UP,
}
