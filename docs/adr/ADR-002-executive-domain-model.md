# ADR-002 — Executive Domain Model for V1 (CRM, interview, meetings, office, workflows)

> **Status:** Accepted · **Date:** 2026-07-28 · **Phase:** V1 (MVP Premium, first real user)

## Context

Until now EMEFA held business knowledge in three shallow places: a ten-field
`business_profiles` row, a flat `memories` list, and a `prospects` pipeline. That was enough
for a demo, and not enough for the product mandate: *an executive must be able to ask a
question out loud and receive an answer a good assistant would give*.

Concretely, none of the questions the mission brief lists as the point of the product could
be answered from stored data:

- « Quels clients dois-je relancer ? » — no notion of last contact.
- « Quels devis attendent une réponse ? » — no quotations.
- « Quels contrats expirent bientôt ? » — no contracts.
- « Quels projets sont bloqués ? » — no projects.
- « Où en est le projet X ? » — nothing to join.

The same gap made every "module" feel separate: documents did not know about clients, tasks
did not come from meetings, briefs could only list open tasks.

Two further constraints shaped the decision. Onboarding had to be an interview, not a form
(mission §1), and the office suite had to produce genuinely professional, still-editable
files without welding business logic to one engine (`CLAUDE.md` §19).

## Decision

**1. A small relational core, not a graph database.**
Five linked tables — `contacts`, `projects`, `deals`, `contracts`, `interactions` — carry
the business relationships, in the existing SQLite database, under the ADR-001 scoping rule.
The "relational memory" the product needs is a *query* (`CrmRepository.lookup`) that walks
those links, not a separate storage engine.

**2. Executive read models live in the domain, and are deterministic.**
`follow_ups`, `awaiting_deals`, `expiring_contracts`, `blocked_projects`, `overview` and
`lookup` compute from stored rows. No model call takes part in deciding that a contract is
expiring. The assistant may *phrase* the answer; it never invents the facts (§25, §33).

**3. Onboarding progress is derived, never stored twice.**
The interview reads the executive profile it feeds. Only two facts are persisted — which
topics were skipped, and when the interview was declared finished. Anything EMEFA learns in
ordinary conversation therefore counts as progress, and a known field can never be asked for
again.

**4. The office capability is a spec + provider boundary.**
Callers build `DocumentSpec` / `WorkbookSpec` / `DeckSpec`; a provider renders them. The
default `PythonOfficeProvider` uses python-docx, openpyxl and python-pptx. Two product rules
are encoded in the boundary rather than left to the engine: files stay **editable** (no
flattening), and spreadsheet formulas stay **live** (a `=` cell is written as a formula, and
totals are generated as real `SUM` ranges).

**5. Workflows compose governed skills and stop at the approval gate.**
`WorkflowEngine` runs the full chain for a scenario (find the client, recall history, write
the document, register the quotation, create the follow-up, draft the e-mail) and returns a
`proposed_action` describing the single consequential step left. It never calls a
COMMUNICATE-risk tool itself, so no workflow can become an automatic mailer (§24, §29).

**6. Meetings are a write-through capability.**
Capturing a meeting performs six verified effects (minutes, decisions, actions, tasks,
project update, chronology entry) and reports each with its identifier, so the assistant can
state what actually happened.

## Alternatives considered

- **A graph database for relational memory.** Rejected: the relationships are a handful of
  foreign keys with a fixed shape. A second datastore would add operations cost and a
  migration path for no answer we cannot already give. Revisit if entity types become
  user-definable.
- **Extending `prospects` instead of adding `contacts`.** Rejected: `prospects` models a
  sales pipeline stage machine, not a durable relationship with quotations, contracts and
  history. It is kept working and untouched; migrating it into the CRM is a separate,
  reversible step.
- **A single polymorphic `crm_save(kind, …)` skill.** Rejected: polymorphic tool schemas
  degrade model tool-selection accuracy. Seven explicitly typed skills are clearer to the
  brain and to the audit log.
- **OfficeCLI as the office engine now.** Deferred, not rejected. The provider boundary
  exists precisely so it can be adopted (or added alongside) without touching callers; doing
  it now would add an external process dependency before we have measured a need.
- **Regenerating documents as PDF.** Rejected for V1: the executive asked for files that stay
  modifiable. PDF export becomes an additional output, never a replacement.

## Consequences

**Positive.** Every capability now reads from one shared business picture, which is what
makes the product feel like one assistant. Briefs, workflows and meeting capture all became
possible with no new provider and no new infrastructure.

**Costs and risks.**

- The governed tool shelf grew to ~40 skills. That is a real risk to tool-selection quality
  on smaller models, and is the main V2 concern: it wants progressive disclosure (expose a
  capability group, then its tools) rather than one flat list.
- `lookup` resolves entities by fuzzy name matching. It is forgiving, which is right for
  conversation, but it can pick the wrong "Horizon" when two exist. Ambiguity reporting is
  V2 work.
- Five new tables mean five more places to enforce tenancy at platformization. They all carry
  their scope columns already, per ADR-001.
- SQLite remains adequate at this size; the read models are indexed single-table scans. This
  decision does not settle the eventual database choice.

## Revisit when

- Tool-selection errors appear in evaluations → introduce skill grouping/routing.
- A second user or organization is onboarded → tenancy enforcement review.
- Document volume or template complexity outgrows python-docx → evaluate OfficeCLI behind the
  existing provider interface, with side-by-side output comparison.
- Entity relationships become user-definable → re-examine the graph-store alternative.
