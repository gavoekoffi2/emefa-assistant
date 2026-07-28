"""Salience scoring — which facts are worth the prompt budget right now.

Design informed by Jarvis OS (AGPL-3.0); implementation original — see
`docs/adr/ADR-004-external-project-licensing.md`.

    score = importance x recency x relevance x confidence

The four factors answer four different questions, and dropping any one of them
produces a failure you can name:

* **importance** — does this kind of claim matter at all? Without it, "le café
  était froid" competes with "l'entreprise vend des panneaux solaires".
* **recency** — is it still true? Half-life comes from the fact's category, so
  a stated goal fades over a year while a dated commitment fades in a
  fortnight.
* **relevance** — is it about what was just asked? BM25 over the fact text.
* **confidence** — have we heard it more than once? A single offhand remark
  should not outrank something confirmed three times.

Multiplying rather than adding is deliberate: a factor near zero must be able
to veto. A perfectly worded match to a fact we barely believe, about something
that stopped being true a year ago, should not surface.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from emefa.domain.memory.kernel import MemoryKernel
from emefa.domain.memory.schemas import DecayPolicy, Fact, FactStatus, ScoredFact

#: Half-life in days per decay policy — after this long, recency has halved.
HALF_LIFE_DAYS: dict[DecayPolicy, float] = {
    DecayPolicy.NONE: math.inf,
    DecayPolicy.VERY_SLOW: 730.0,
    DecayPolicy.SLOW: 365.0,
    DecayPolicy.MEDIUM: 90.0,
    DecayPolicy.FAST: 14.0,
}

#: BM25 magnitude beyond which a hit is treated as no better than noise.
_BM25_CAP = 20.0

#: Relevance given to a fact that had no text hit at all. Non-zero so that a
#: cold start, or a question sharing no vocabulary with the memory, still
#: surfaces the durably important things (who the user is, what they sell)
#: instead of returning nothing.
_NO_MATCH_RELEVANCE = 0.25


class MemoryRetrieval:
    def __init__(self, kernel: MemoryKernel) -> None:
        self.kernel = kernel

    def retrieve(
        self,
        query: str = "",
        limit: int = 8,
        now: datetime | None = None,
        entity_id: str | None = None,
        personal_only: bool = False,
    ) -> list[ScoredFact]:
        """`personal_only` restricts the result to facts about the user
        themselves — the ones with no owning entity.

        This is what keeps business memory out of the personal prompt block. A
        project's budget belongs in that project's brief, fetched when asked
        for; injecting it into every turn is both a leak and a waste.
        """
        reference = now or datetime.now(timezone.utc)

        def in_scope(fact: Fact) -> bool:
            if entity_id is not None:
                return fact.entity_id == entity_id
            return fact.entity_id is None if personal_only else True

        candidates: dict[str, tuple[Fact, float]] = {}
        for fact, bm25 in self.kernel.search(query, limit=limit * 4):
            if fact.status is FactStatus.ACTIVE and in_scope(fact):
                candidates[fact.fact_id] = (fact, _relevance(bm25))

        # Always consider the durably important facts alongside the text hits.
        # Identity and offer rarely share words with a question ("prépare le
        # devis") yet are almost always needed to answer it well.
        for fact in self.kernel.list_facts(
            FactStatus.ACTIVE,
            limit=limit * 4,
            entity_id=entity_id,
            personal_only=personal_only,
        ):
            candidates.setdefault(fact.fact_id, (fact, _NO_MATCH_RELEVANCE))

        scored = [
            ScoredFact(
                fact=fact,
                score=fact.importance * _recency(fact, reference) * relevance * fact.confidence,
                relevance=relevance,
                recency=_recency(fact, reference),
            )
            for fact, relevance in candidates.values()
        ]
        scored.sort(key=lambda item: (-item.score, item.fact.fact_id))
        top = scored[:limit]

        return [
            ScoredFact(
                fact=item.fact,
                score=item.score,
                relevance=item.relevance,
                recency=item.recency,
                superseded=tuple(self.kernel.superseded_by(item.fact.fact_id)),
            )
            for item in top
        ]

    def context_block(
        self,
        query: str = "",
        limit: int = 8,
        max_chars: int = 200,
        now: datetime | None = None,
    ) -> str:
        """Bounded memory block for the system prompt. Empty when nothing is
        remembered — an empty section is worse than no section, because the
        model reads it as "this user has no history".

        Personal facts only. What is known about a project or a client is
        reached deliberately, through its brief.
        """
        facts = self.retrieve(query, limit=limit, now=now, personal_only=True)
        if not facts:
            return ""
        lines = ["Mémoire durable (l'utilisateur peut la consulter et l'effacer) :"]
        for item in facts:
            line = f"- [{item.fact.category}] {item.fact.render()[:max_chars]}"
            if item.superseded:
                previous = item.superseded[0].object[:60]
                line += f" (auparavant : {previous})"
            lines.append(line)
        return "\n".join(lines)


def _relevance(bm25: float) -> float:
    """BM25 (negative and lower is better in FTS5) mapped onto [0, 1]."""
    if bm25 == 0.0:
        return _NO_MATCH_RELEVANCE
    return max(0.0, min(1.0, math.exp(-min(abs(bm25), _BM25_CAP) / _BM25_CAP)))


def _recency(fact: Fact, now: datetime) -> float:
    half_life = HALF_LIFE_DAYS.get(fact.decay_policy, 90.0)
    if half_life == math.inf:
        return 1.0
    age_days = max(0.0, (now - _parse(fact.last_seen_at)).total_seconds() / 86_400.0)
    return 0.5 ** (age_days / half_life)


def _parse(timestamp: str) -> datetime:
    """Tolerate both the kernel's ISO timestamps and SQLite's
    `CURRENT_TIMESTAMP` default, which rows migrated from the flat store
    carry."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
