"""Durable memory — the facade the rest of EMEFA talks to.

Backed by the memory kernel (ADR-003): atomic dated sourced facts, reinforced
by re-observation, superseded rather than deleted when contradicted, and
retrieved by computed salience rather than by recency.

The public surface that existed before the kernel — `remember`, `list_all`,
`forget`, `context_block`, and the `Memory` shape — is preserved exactly, so
the agent tools, the HTTP API and every stored `memory_id` keep working. The
kernel is reachable underneath for callers that need facts rather than lines.

Two write paths, deliberately different:

* `remember()` is an explicit instruction — the user, or the assistant on the
  user's behalf, said *store this*. It always stores, and only collapses an
  exact repeat.
* `record_fact()` is the extraction path. It reconciles: a restated claim
  reinforces, a changed one supersedes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emefa.domain.memory import vocabulary
from emefa.domain.memory.kernel import MemoryKernel
from emefa.domain.memory.retrieval import MemoryRetrieval
from emefa.domain.memory.schemas import Fact, FactStatus, MemoryEvent

#: Categories accepted by `remember`. Kept as a flat tuple because the agent
#: tool schema and the API both advertise it.
CATEGORIES: tuple[str, ...] = tuple(vocabulary.CATEGORIES)

MAX_CONTENT_CHARS = 500


@dataclass(frozen=True, slots=True)
class Memory:
    """A fact rendered as the line a human reads."""

    memory_id: str
    category: str
    content: str
    source: str
    created_at: str


def _as_memory(fact: Fact) -> Memory:
    return Memory(
        memory_id=fact.fact_id,
        category=fact.category,
        content=fact.render(),
        source=fact.source,
        created_at=fact.created_at,
    )


class MemoryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.kernel = MemoryKernel(database_path)
        self.retrieval = MemoryRetrieval(self.kernel)

    # ── explicit writes ───────────────────────────────────────────────────

    def remember(
        self, content: str, category: str = "fact", source: str = "conversation"
    ) -> Memory:
        cleaned = " ".join(content.split()).strip()[:MAX_CONTENT_CHARS]
        if not cleaned:
            raise ValueError("memory content must not be empty")
        category = vocabulary.normalise_category(category)

        # An exact repeat is evidence, not a second memory.
        duplicate = self._exact_duplicate(cleaned, category)
        if duplicate is not None:
            reinforced = self.kernel.reinforce(duplicate.fact_id)
            return _as_memory(reinforced or duplicate)

        event = self.kernel.log_event(
            type="memory_written",
            source=source,
            content=cleaned,
            metadata={"category": category},
        )
        fact = self.kernel.insert_fact(
            subject=vocabulary.DEFAULT_SUBJECT,
            predicate=vocabulary.NEUTRAL_PREDICATE,
            object=cleaned,
            category=category,
            source=source,
            source_event_id=event.event_id,
        )
        return _as_memory(fact)

    def record_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        category: str,
        *,
        source: str = "extraction",
        event_id: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[Fact, str]:
        """Reconciling write. Returns the resulting fact and what happened:
        `created`, `reinforced` or `superseded`."""
        category = vocabulary.normalise_category(category)
        predicate = vocabulary.normalise_predicate(predicate, category)
        subject = vocabulary.normalise_term(subject) or vocabulary.DEFAULT_SUBJECT
        cleaned = " ".join(object.split()).strip()[:MAX_CONTENT_CHARS]
        if not cleaned:
            raise ValueError("fact object must not be empty")

        existing = self.kernel.find_active_match(subject, predicate, category, entity_id)

        if existing is not None and vocabulary.normalise_term(
            existing.object
        ) == vocabulary.normalise_term(cleaned):
            reinforced = self.kernel.reinforce(existing.fact_id, event_id)
            return (reinforced or existing), "reinforced"

        fact = self.kernel.insert_fact(
            subject=subject,
            predicate=predicate,
            object=cleaned,
            category=category,
            source=source,
            source_event_id=event_id,
            entity_id=entity_id,
        )

        # Two conditions must both hold for a claim to replace an earlier one.
        #
        # The predicate must be structured: an unstructured note carries no
        # claim another note could contradict, so two remarks coexist.
        #
        # And the category must not be one that accumulates: a project has one
        # current objective, but many decisions and many open problems, and
        # erasing a decision because a later one exists destroys the record of
        # how the project got where it is.
        if (
            existing is not None
            and predicate != vocabulary.NEUTRAL_PREDICATE
            and category not in vocabulary.ACCUMULATING_CATEGORIES
        ):
            self.kernel.supersede(existing.fact_id, fact, event_id)
            return fact, "superseded"
        return fact, "created"

    def log_event(
        self,
        type: str,
        source: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        return self.kernel.log_event(type, source, content, metadata)

    # ── reads ─────────────────────────────────────────────────────────────

    def get(self, memory_id: str) -> Memory | None:
        fact = self.kernel.get_fact(memory_id)
        return _as_memory(fact) if fact is not None else None

    def list_all(self, limit: int = 100) -> list[Memory]:
        facts = self.kernel.list_facts(FactStatus.ACTIVE, limit=limit)
        return [_as_memory(fact) for fact in facts]

    def search(self, query: str, limit: int = 8) -> list[Memory]:
        return [_as_memory(item.fact) for item in self.retrieval.retrieve(query, limit=limit)]

    def history(self, memory_id: str) -> dict[str, Any] | None:
        """What we believed before, and how we became confident. The
        user-facing answer to "why do you think that?"."""
        fact = self.kernel.get_fact(memory_id)
        if fact is None:
            return None
        return {
            "memory_id": fact.fact_id,
            "content": fact.render(),
            "category": fact.category,
            "status": fact.status.value,
            "confidence": round(fact.confidence, 3),
            "support_count": fact.support_count,
            "created_at": fact.created_at,
            "last_seen_at": fact.last_seen_at,
            "observations": [
                {
                    "type": observation.observation_type.value,
                    "at": observation.created_at,
                    "delta": round(observation.confidence_delta, 3),
                }
                for observation in self.kernel.list_observations(memory_id)
            ],
            "replaced": [
                {"content": previous.render(), "until": previous.updated_at}
                for previous in self.kernel.superseded_by(memory_id)
            ],
        }

    def stats(self) -> dict[str, int]:
        return {
            "events": self.kernel.count_events(),
            "active_facts": self.kernel.count_facts(FactStatus.ACTIVE),
            "superseded_facts": self.kernel.count_facts(FactStatus.SUPERSEDED),
        }

    # ── corrections and deletion ──────────────────────────────────────────

    def correct(self, memory_id: str, content: str) -> Memory | None:
        corrected = self.kernel.correct(memory_id, content)
        return _as_memory(corrected) if corrected is not None else None

    def forget(self, memory_id: str) -> bool:
        return self.kernel.forget(memory_id)

    # ── prompt context ────────────────────────────────────────────────────

    def context_block(self, max_items: int = 12, max_chars: int = 200, query: str = "") -> str:
        return self.retrieval.context_block(query=query, limit=max_items, max_chars=max_chars)

    # ── internals ─────────────────────────────────────────────────────────

    def _exact_duplicate(self, content: str, category: str) -> Fact | None:
        target = vocabulary.normalise_term(content)
        for fact in self.kernel.list_facts(FactStatus.ACTIVE, category=category, limit=200):
            if vocabulary.normalise_term(fact.object) == target:
                return fact
        return None
