"""Answering with context instead of with facts.

"Où en est le projet Graphiste GPT ?" is not a search. The useful answer names
the client it is for, what was decided, what is still open, what was last
done, and what happens next — which means walking the graph, not ranking
strings.

Two deliberate limits:

* **One hop, then stop.** The client of a project is context; the client's
  other projects' invoices are noise. Depth is where graph answers turn into
  walls of text.
* **Nothing is generated.** Everything below is assembled from what was
  recorded. A brief that invents a status is worse than no brief, because the
  user cannot tell which is which.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from emefa.domain.entities.schemas import (
    DECISION_CATEGORY,
    ISSUE_CATEGORY,
    KIND_LABELS,
    MILESTONE_LABELS,
    Entity,
    EntityStatus,
    Milestone,
    RelationKind,
)
from emefa.domain.entities.store import EntityRepository
from emefa.domain.memories import MemoryRepository
from emefa.domain.memory.schemas import FactStatus

#: How many facts of each kind a brief carries. A brief that lists forty
#: decisions is a database dump, not a brief.
MAX_PER_SECTION = 8
MAX_TIMELINE_IN_BRIEF = 6

_RELATION_LABELS: dict[tuple[RelationKind, str], str] = {
    (RelationKind.CLIENT_OF, "in"): "Client",
    (RelationKind.CLIENT_OF, "out"): "Client de",
    (RelationKind.SUPPLIER_OF, "in"): "Fournisseur",
    (RelationKind.SUPPLIER_OF, "out"): "Fournisseur de",
    (RelationKind.PARTNER_OF, "out"): "Partenaire",
    (RelationKind.PARTNER_OF, "in"): "Partenaire",
    (RelationKind.WORKS_FOR, "in"): "Collaborateur",
    (RelationKind.WORKS_FOR, "out"): "Travaille pour",
    (RelationKind.BELONGS_TO, "out"): "Rattaché à",
    (RelationKind.BELONGS_TO, "in"): "Comprend",
    (RelationKind.COVERS, "out"): "Porte sur",
    (RelationKind.COVERS, "in"): "Couvert par",
    (RelationKind.SETTLES, "out"): "Règle",
    (RelationKind.SETTLES, "in"): "Réglé par",
    (RelationKind.ABOUT, "out"): "À propos de",
    (RelationKind.ABOUT, "in"): "Concerné par",
    (RelationKind.ATTENDED_BY, "out"): "Avec",
    (RelationKind.ATTENDED_BY, "in"): "A participé à",
    (RelationKind.RELATED_TO, "out"): "Lié à",
    (RelationKind.RELATED_TO, "in"): "Lié à",
}


@dataclass(frozen=True, slots=True)
class EntityBrief:
    entity: Entity
    objectives: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    open_issues: tuple[str, ...] = ()
    other_facts: tuple[str, ...] = ()
    #: (label, entity) pairs — "Client : Horizon SARL".
    related: tuple[tuple[str, Entity], ...] = ()
    recent: tuple[dict[str, Any], ...] = ()
    next_milestone: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            **self.entity.summary_dict(),
            "objectives": list(self.objectives),
            "decisions": list(self.decisions),
            "open_issues": list(self.open_issues),
            "other_facts": list(self.other_facts),
            "related": [
                {"relation": label, **other.summary_dict()} for label, other in self.related
            ],
            "recent": list(self.recent),
            "next_milestone": self.next_milestone,
        }

    def as_text(self) -> str:
        """The answer EMEFA reads aloud. Sections that are empty are omitted
        rather than printed as "aucun" — an assistant listing what it does not
        know sounds like a form."""
        label = KIND_LABELS.get(self.entity.kind, self.entity.kind.value)
        head = f"{label} {self.entity.name} — {_STATUS_WORDS[self.entity.status]}"
        lines = [head]
        if self.entity.summary:
            lines.append(self.entity.summary)
        if self.related:
            lines.append(
                "Rattachements : "
                + ", ".join(f"{name} : {other.name}" for name, other in self.related)
            )
        for title, items in (
            ("Objectifs", self.objectives),
            ("Décisions", self.decisions),
            ("Problèmes ouverts", self.open_issues),
        ):
            if items:
                lines.append(f"{title} :")
                lines.extend(f"- {item}" for item in items)
        if self.recent:
            lines.append("Derniers évènements :")
            lines.extend(
                f"- {item['occurred_at'][:10]} · {item['label']} : {item['headline']}"
                for item in self.recent
            )
        if self.next_milestone:
            lines.append(f"Étape suivante attendue : {self.next_milestone}")
        return "\n".join(lines)


_STATUS_WORDS = {
    EntityStatus.ACTIVE: "en cours",
    EntityStatus.ON_HOLD: "en pause",
    EntityStatus.DONE: "terminé",
    EntityStatus.CLOSED: "clos",
}


class EntityGraph:
    def __init__(self, entities: EntityRepository, memories: MemoryRepository) -> None:
        self.entities = entities
        self.memories = memories

    # ── writing ───────────────────────────────────────────────────────────

    def note(
        self,
        entity_id: str,
        content: str,
        category: str = "note",
        predicate: str | None = None,
    ) -> str:
        """Attach a fact to an entity.

        Goes through the memory kernel, so an entity's memory inherits
        everything already built there — reinforcement, supersession, decay —
        scoped so one project's objective never supersedes another's.
        """
        fact, _ = self.memories.record_fact(
            subject="entite",
            # None lets the category choose: an objective gets a structured
            # predicate and can therefore replace an earlier objective, while a
            # decision keeps accumulating.
            predicate=predicate,
            object=content,
            category=category,
            source="entity",
            entity_id=entity_id,
        )
        return fact.fact_id

    # ── reading ───────────────────────────────────────────────────────────

    def facts_for(self, entity_id: str, category: str | None = None) -> list:
        return self.memories.kernel.list_facts(
            FactStatus.ACTIVE, category=category, limit=200, entity_id=entity_id
        )

    def brief(self, entity_id: str) -> EntityBrief | None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return None

        facts = self.facts_for(entity_id)
        by_category: dict[str, list[str]] = {}
        for fact in facts:
            by_category.setdefault(fact.category, []).append(fact.render())

        decisions = tuple(by_category.get(DECISION_CATEGORY, [])[:MAX_PER_SECTION])
        issues = tuple(by_category.get(ISSUE_CATEGORY, [])[:MAX_PER_SECTION])
        objectives = tuple(by_category.get("goal", [])[:MAX_PER_SECTION])
        other = tuple(
            line
            for category, lines in by_category.items()
            if category not in {DECISION_CATEGORY, ISSUE_CATEGORY, "goal"}
            for line in lines
        )[:MAX_PER_SECTION]

        related = tuple(
            (_RELATION_LABELS.get((relation.kind, direction), "Lié à"), other_entity)
            for relation, other_entity, direction in self.entities.relations_of(entity_id)
        )

        history = self.entities.timeline(entity_id)
        recent = tuple(entry.summary() for entry in history[-MAX_TIMELINE_IN_BRIEF:])

        return EntityBrief(
            entity=entity,
            objectives=objectives,
            decisions=decisions,
            open_issues=issues,
            other_facts=other,
            related=related,
            recent=recent,
            next_milestone=next_expected(history),
        )

    def brief_by_name(self, name: str, kind: str | None = None) -> EntityBrief | None:
        entity = self.entities.resolve(name, kind)
        return self.brief(entity.entity_id) if entity is not None else None


def next_expected(history: list) -> str:
    """The milestone that usually comes after the furthest one reached.

    A suggestion drawn from the ordinary shape of a commercial relationship,
    not a prediction. It is labelled as expected, never as scheduled.
    """
    from emefa.domain.entities.schemas import MILESTONE_ORDER

    reached = {entry.milestone for entry in history}
    furthest = -1
    for index, milestone in enumerate(MILESTONE_ORDER):
        if milestone in reached:
            furthest = index
    if furthest < 0 or furthest + 1 >= len(MILESTONE_ORDER):
        return ""
    return MILESTONE_LABELS[MILESTONE_ORDER[furthest + 1]]
