"""Data contracts for the memory kernel (ADR-003).

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FactStatus(StrEnum):
    #: Currently believed.
    ACTIVE = "active"
    #: Replaced by a newer, contradicting fact. Kept forever so the assistant
    #: can say what changed and when.
    SUPERSEDED = "superseded"
    #: Contradicted with no clear winner — surfaced to the user rather than
    #: guessed at.
    NEEDS_REVIEW = "needs_review"


class DecayPolicy(StrEnum):
    """How fast a claim stops being worth surfacing. Half-lives in retrieval."""

    NONE = "none"
    VERY_SLOW = "very_slow"
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"


class ObservationType(StrEnum):
    CREATED = "created"
    REINFORCED = "reinforced"
    WEAKENED = "weakened"
    CORRECTED = "corrected"
    SUPERSEDED = "superseded"


class RelationType(StrEnum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    RELATED_TO = "related_to"


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    """Immutable record of something that happened. Never deleted."""

    event_id: str
    type: str
    source: str
    content: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Fact:
    """One atomic claim, dated and sourced."""

    fact_id: str
    subject: str
    predicate: str
    object: str
    category: str
    status: FactStatus
    confidence: float
    support_count: int
    importance: float
    decay_policy: DecayPolicy
    source: str
    source_event_id: str | None
    #: The project, company or person this fact is about. None means it is
    #: about the user themselves — personal memory.
    entity_id: str | None
    created_at: str
    last_seen_at: str
    updated_at: str

    def render(self) -> str:
        """Human-readable form.

        A `note` carries its whole meaning in the object — it is the text the
        user actually wrote — so it renders bare. So does anything attached to
        an entity: the project *is* the subject, and repeating "projet" in
        front of every line about it is noise. Everything else renders as the
        triple with the predicate's underscores opened back out.
        """
        if self.predicate == "note" or self.entity_id is not None:
            return self.object
        return f"{self.subject} {self.predicate.replace('_', ' ')} {self.object}"

    def search_text(self) -> str:
        """Indexed representation. Category is included so a query naming a
        domain ("préférence", "objectif") reaches the right facts even when it
        shares no word with them."""
        return f"{self.subject} {self.predicate.replace('_', ' ')} {self.object} {self.category}"


@dataclass(frozen=True, slots=True)
class FactObservation:
    """One re-observation of a fact. This is what makes memory reinforce
    instead of duplicate."""

    observation_id: str
    fact_id: str
    event_id: str | None
    observation_type: ObservationType
    confidence_delta: float
    created_at: str


@dataclass(frozen=True, slots=True)
class FactRelation:
    relation_id: str
    from_fact_id: str
    to_fact_id: str
    relation_type: RelationType
    created_at: str


@dataclass(frozen=True, slots=True)
class ScoredFact:
    """A retrieved fact with the components of its salience, kept separate so
    ranking decisions are inspectable instead of a single opaque number."""

    fact: Fact
    score: float
    relevance: float
    recency: float
    superseded: tuple[Fact, ...] = ()


#: Confidence a fact starts life with. Below 1.0 because a single mention is
#: evidence, not proof; reinforcement is what earns certainty.
INITIAL_CONFIDENCE = 0.6
#: Confidence gained per re-observation, and lost per contradiction.
REINFORCEMENT_STEP = 0.12
WEAKENING_STEP = 0.25
#: A fact never reaches 1.0 — the user is always allowed to have changed.
MAX_CONFIDENCE = 0.98
MIN_CONFIDENCE = 0.05
