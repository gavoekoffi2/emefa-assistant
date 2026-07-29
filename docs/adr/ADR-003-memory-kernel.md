# ADR-003 — Memory Kernel: atomic facts instead of stored sentences

> **Status:** Accepted · **Date:** 2026-07-28

## Context

EMEFA's memory is a `memories` table of free-text rows (`category`, `content`, `source`,
`created_at`). The context block injected into the brain is the twelve most recent rows,
verbatim. Three failures follow directly from that shape:

- **It rots.** The same fact restated three times becomes three rows, each competing for
  the twelve slots.
- **It cannot be corrected.** When the user changes their mind, the old row stays and both
  versions are injected; the assistant contradicts itself.
- **It is chronological, not salient.** A throwaway remark from this morning displaces the
  company's core offer stated last month.

CLAUDE.md §26 already forbids "save every conversation forever" and requires relevance,
confidence, provenance, expiration and user control. The current implementation delivers
provenance and user control only.

`jarvis-OS` solves this with a Memory Kernel whose design is sound and is adopted
conceptually (implementation is original — see ADR-004).

## Decision

Memory becomes a **fact store**, with SQLite as the single source of truth, inside EMEFA's
existing numbered-migration scheme.

1. **Four tables plus a full-text index.**
   - `memory_events` — immutable log of everything that happened (turns, observations,
     mission lessons). Never deleted.
   - `memory_facts` — atomic claims `(subject, predicate, object, category)` with
     `status`, `confidence`, `support_count`, `importance`, `decay_policy`, `valid_from`,
     `valid_to`, the source event, and `last_seen_at`.
   - `memory_fact_observations` — one row per re-observation. Reinforcement without
     duplication.
   - `memory_fact_relations` — `supersedes` / `contradicts` / `supports` / `related_to`.
   - `memory_facts_fts` — FTS5 over the concatenated fact text, `unicode61` with
     diacritics removed (mandatory for French).

2. **Never delete a contradicted fact.** It is marked `superseded` and linked to its
   successor. User-initiated deletion is a distinct, explicit path (`forget`) and is the
   only operation that removes rows — CLAUDE.md §26 requires the user can delete.

3. **Closed vocabulary.** Predicates and categories come from a fixed enumeration defined
   in code. Free-form predicates from an LLM make matching impossible, which is what makes
   reinforcement and supersession work at all.

4. **Computed salience.**
   `score = importance × recency × relevance × confidence`, where `recency` is a half-life
   decay whose period is set by the fact's `decay_policy` (`none`, `very_slow`, `slow`,
   `medium`, `fast`) and `relevance` comes from FTS5 BM25. Retrieval returns the top-k plus
   the facts they supersede, so the assistant can reason about what changed.

5. **Vectors are deferred.** FTS5 alone, for now. Embeddings add a provider dependency, a
   per-write cost and an index to maintain; the gain over BM25 on a few thousand short
   French facts is unproven. Revisit with a measurement, not an impression (CLAUDE.md §37).

6. **Migration, not replacement.** The existing `memories` rows are migrated into
   `memory_facts` as `category='other'` facts with their original text as the object and
   provenance preserved. The current `remember` / `list_memories` / `forget` tools keep
   working against the new store; no user loses a memory and no API breaks.

7. **Tenant scoping from day one.** Every table carries `tenant_id` and `user_id`. No query
   without an owning scope.

## Alternatives considered

- **Keep the flat table, just retrieve better.** Rejected: no amount of ranking fixes
  duplication or contradiction, which are the two failures users actually notice.
- **Store raw conversation and RAG over it.** Rejected by CLAUDE.md §26 and by cost: it
  re-reads noise forever and can never answer "what does she believe about me now".
- **Vector store from the start.** Rejected for this slice: unproven benefit, real cost,
  and it can be added behind the same retrieval interface later.
- **Graph database.** Rejected: the relation count is small; SQLite with a relations table
  covers it without a second engine to operate.

## Consequences

- Memory writes get more expensive (extraction + reconciliation) and are therefore moved
  off the request path where possible, into the ingestion pass.
- The retrieval interface becomes the single place memory enters a prompt, which is also
  where the injected block is bounded.
- Contradiction history is auditable, which is a product feature ("tu m'avais dit…"), not
  only a technical property.
- Extraction quality is now the limiting factor for memory quality. It needs evaluation
  cases (CLAUDE.md §37), tracked in the backlog.

## Revisit conditions

Fact count beyond a few tens of thousands per user, measured BM25 recall failures on
French/Ewe code-switching, or a need for cross-language recall triggers the embeddings ADR.
