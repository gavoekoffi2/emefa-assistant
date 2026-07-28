# ADR-004 — Re-implement rather than copy: AGPL exposure from jarvis-OS

> **Status:** Accepted · **Date:** 2026-07-28

## Context

EMEFA is adopting capabilities demonstrated by two external repositories:

| Repository | Licence |
|---|---|
| `github.com/Grominet95/jarvis-OS` | **GNU AGPL-3.0-or-later** |
| `github.com/Grominet95/jarvis-skills` | **MIT** |

EMEFA ships no `LICENSE` file and is being built as a commercial product for
entrepreneurs and SMEs.

AGPL-3.0 is a strong copyleft licence. A work that copies or adapts AGPL source is a
derivative work and must itself be distributed under AGPL-3.0. §13 goes further than the
GPL: **running** a modified version on a network server obliges the operator to offer the
complete corresponding source to every user interacting with it remotely. For a hosted
assistant, that is every customer.

This is not a reversible decision. Once AGPL code is merged and shipped, the obligation
attaches, and removing the files later does not retroactively cure distributions already
made.

Independently of licensing, a direct port would not function: jarvis-OS assumes a single
local user, a `.env` file on disk, a local microphone, a local LiveKit binary, a local
SQLite path and one hard-coded Telegram owner id. EMEFA is a multi-tenant-ready hosted
web/PWA product.

## Decision

1. **No source from `jarvis-OS` enters EMEFA.** No file, no function body, no comment, no
   docstring, no schema DDL transcribed verbatim or lightly edited.
2. **Designs are adopted; implementations are original.** Architecture, data-model shape,
   algorithms and product behaviour are not protected by copyright. EMEFA re-implements
   them in its own idiom, against its own schema, with its own tenant scoping, its own
   naming and its own tests.
3. **`jarvis-skills` (MIT) may be reused directly**, including its manifest schema,
   catalogue index format and skill prompts, provided the MIT notice and copyright line
   travel with the reused material. Reused MIT content is isolated under a directory
   carrying a `NOTICE` file.
4. **Attribution regardless.** `docs/CREDITS.md` records the design debt to both projects
   and their authors, even where no code is reused and none is legally required.
5. **EMEFA remains unlicensed (proprietary) unless the owner decides otherwise.** This ADR
   does not choose EMEFA's licence; it preserves the owner's freedom to choose it.

## Alternatives considered

- **Copy jarvis-OS and release EMEFA under AGPL-3.0.** A legitimate choice — it is fast and
  fully lawful. Rejected as a *default* because it is irreversible and forecloses the
  commercial model without the owner having deliberately chosen it. If the owner does
  choose AGPL later, nothing done under this ADR needs undoing.
- **Copy and not comply.** Rejected: unlawful.
- **Use jarvis-OS as a separate service and call it over HTTP.** Mitigates §5 of the AGPL
  (aggregation) but not §13 for the deployed instance, and it would mean operating a second
  runtime with its own auth model, database and lifecycle for capabilities EMEFA needs
  inside its own request path. Rejected on operational grounds as much as legal ones.

## Consequences

- Implementation is slower than a port. This is the accepted cost of the owner keeping the
  licence choice open.
- Where jarvis-OS's shape is genuinely the best known design (fact reinforcement,
  supersession, autonomy levels), EMEFA's version will resemble it structurally. That is
  expected and lawful; the guard is that no source is transcribed.
- Reviewers must be able to check the rule. Every subsystem adopted this way names its
  design source in its module docstring.

## Revisit conditions

The owner deciding EMEFA's licence — in either direction — retires or rewrites this ADR. A
decision to publish EMEFA under AGPL-3.0 would permit direct reuse and should be recorded
as a superseding ADR before any code is copied.
