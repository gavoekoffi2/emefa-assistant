# Gap analysis — jarvis-OS / jarvis-skills → EMEFA

> **Date:** 2026-07-28 · **Status:** audit complete, implementation in progress
> **Sources audited:**
> - `github.com/Grominet95/jarvis-OS` — 220 Python files, 36 239 LOC, **AGPL-3.0-or-later**
> - `github.com/Grominet95/jarvis-skills` — 81 files, catalogue of skills/presets/views, **MIT**
> - EMEFA `backend/` — 44 Python modules, 7 696 LOC, 107 tests passing
>
> Both repositories were cloned and read. This document records what they actually
> contain, not what their READMEs claim.

---

## 0. Executive summary

jarvis-OS is a mature single-user, self-hosted desktop assistant. Its genuinely
strong subsystems — the ones EMEFA lacks and should acquire — are:

1. **Memory Kernel** — atomic, dated, sourced, reinforceable facts with contradiction
   handling and a real retrieval score. EMEFA's memory is a flat list of strings.
2. **Governed proactive engine** — initiatives carrying an autonomy level 0–5, a cost
   ceiling, a permission category and a lifecycle. EMEFA has one cron-driven briefing.
3. **Mission engine** — plan → step → verify → resume, surviving a crash. EMEFA has a
   4-turn in-request agent loop.
4. **Skills as installable artefacts** — manifest, registry, lifecycle, sandboxed test.
   EMEFA's skills are hard-coded Python in a single 750-line module.
5. **Budget guard + usage tracking + event bus** — EMEFA has none of the three.

Two subsystems must **not** be copied, and this is the single most important finding
of the audit:

- **Authentication.** jarvis-OS authenticates with *one static bearer token* read from
  `.env`, exempts `/admin`, `/dashboard` and **every WebSocket** from auth entirely, and
  injects the token into the HTML page. That is a reasonable design for `127.0.0.1` on a
  personal laptop. Ported to EMEFA — a browser-reachable product — it would be a serious
  regression: EMEFA today already has per-device hashed tokens, `httponly`/`secure`/
  `samesite=strict` cookies, rate-limited enrolment, revocation and audit. **EMEFA's auth
  is stronger and stays.** What EMEFA is genuinely missing is *identity*: real user
  accounts behind the device layer. That is built, not copied (§ ADR-002).
- **Licence.** jarvis-OS is AGPL-3.0. Copying its files into EMEFA would put EMEFA under
  AGPL, including §13 — anyone using EMEFA over a network could demand its source. EMEFA
  ships no licence file, i.e. proprietary. Every subsystem below is therefore
  **re-implemented in EMEFA's own architecture**, from the design, not from the code
  (§ ADR-004). `jarvis-skills` is MIT and *may* be reused directly with attribution.

Beyond the licence, a straight port would not work anyway: jarvis-OS assumes one
local user, a `.env` file, a local SQLite path, a local microphone, a local LiveKit
binary and a Telegram owner ID. EMEFA is a multi-tenant-ready web/PWA product with a
holographic realtime front end. The *ideas* transfer; the code does not.

---

## 1. Subsystem-by-subsystem verdict

| # | Subsystem | jarvis-OS | EMEFA today | Verdict |
|---|---|---|---|---|
| 1 | **Persistent memory** | Memory Kernel: `events`/`facts`/`fact_observations`/`fact_relations` + FTS5; confidence, `support_count`, `importance`, decay policy, supersede-never-delete, Markdown mirror | `memories` table: `category`, `content`, `source`, `created_at`. Context block = last 12 rows verbatim | **REIMPLEMENT — highest priority** |
| 2 | **Fact ingestion** | LLM extraction against a closed vocabulary, reconciliation, reinforcement without duplication | A `remember` tool the model may call | **REIMPLEMENT** |
| 3 | **Nightly consolidation** | AutoDream + ConsolidationAgent re-read recent sessions for missed facts | none | **REIMPLEMENT** |
| 4 | **Retrieval** | `importance × recency(decay) × relevance(BM25) × confidence`, plus known contradictions | `ORDER BY created_at DESC LIMIT 12` | **REIMPLEMENT** |
| 5 | **Identity** | none — single implicit owner | `tenant → user → assistant` hierarchy exists, seeded with constants (ADR-001) | **KEEP + EXTEND** (real accounts) |
| 6 | **Authentication** | single static bearer token; `/admin`, `/dashboard`, all WebSockets exempt | hashed per-device tokens, secure cookies, enrolment code, rate limit, revoke, audit | **KEEP EMEFA'S — reject jarvis-OS's** |
| 7 | **Biometric identification** | face recognition against `vision_data/faces/reference.jpg`, "Wake Up" scan sequence | none | **REIMPLEMENT, reduced scope** — see §3 |
| 8 | **Runtime permissions** | 4 booleans (microphone/screen/camera/files), process-global singleton | risk classes + `RUN`/`ASK`/`BLOCK` policy, per-tool | **KEEP EMEFA'S + EXTEND** with scoped grants |
| 9 | **Approvals** | pending approvals with UI broadcast | `pending_actions` table, survives restart | **KEEP + EXTEND** (session/scoped/persistent grants) |
| 10 | **Skills** | manifest + registry + lifecycle + installer + Docker sandbox lab + synthesizer | 20 tools hard-coded in `skills.py` | **REIMPLEMENT** (registry) |
| 11 | **Skills catalogue** | `jarvis-skills`, MIT: `skill.yaml` schema 1.0, `index.json`, JSON-schema validation | none | **REUSE DIRECTLY** (MIT + attribution) |
| 12 | **Proactive engine** | initiatives, autonomy 0–5, collectors, Command Center, nightly curator | one daily briefing on a cron | **REIMPLEMENT** |
| 13 | **Mission engine** | orchestrator, worker agent, verifier (structural/deterministic/semantic), governance gate, reflexion, resume after crash | `AgentEngine`, max 4 turns, in-request | **REIMPLEMENT** |
| 14 | **Budget** | `BudgetGuard` per scope, thresholds, hard stop; `UsageEntry` cost table | none | **REIMPLEMENT** |
| 15 | **Event bus** | in-process pub/sub, typed events | direct calls | **REIMPLEMENT** |
| 16 | **Audit** | append-only JSONL `AuditEntry` | `audit()` → structured JSON logs | **KEEP + EXTEND** (queryable store) |
| 17 | **Voice** | LiveKit + Deepgram/Whisper + Piper/ElevenLabs, separate process | ElevenLabs realtime, signed URL, working, benchmarked | **KEEP EMEFA'S** — CLAUDE.md §12/§14 forbid replacing before a measured baseline |
| 18 | **Vision** | YOLOv8 screen capture + object detection | none | **DEFER** — no product value proven for EMEFA's users |
| 19 | **Hardware** | macropad firmware, Bluetooth parsers, Arduino CLI | none | **REJECT** — desktop-specific, no EMEFA use case |
| 20 | **Channels** | Telegram bot gated on one owner ID | none | **REIMPLEMENT later** — real value (mobile access), but must be per-user, not one hard-coded ID |
| 21 | **Setup wizard** | web form writing `.env` | conversational onboarding in the agent | **KEEP EMEFA'S** — CLAUDE.md §27 prefers conversational |
| 22 | **Views** | full-screen WebSocket-driven views (globe, weather, clock, system monitor) + MediaPipe gesture bindings | holographic face + universe | **REIMPLEMENT later** — fits the HUD the reference image shows |
| 23 | **Layer enforcement** | `import-linter` contracts in CI, mypy scoped to Protocols | conventions only | **ADOPT** — cheap, and it is what kept jarvis-OS coherent at 36k LOC |

---

## 2. What is worth taking, precisely

### 2.1 Memory Kernel — the design that matters

The valuable idea is not "SQLite for memory". It is these five invariants:

1. **A fact is atomic, typed and sourced.** `(subject, predicate, object, category)`
   plus the id of the event that produced it. Not a sentence.
2. **Re-observing a fact never duplicates it.** It appends a `fact_observation` and
   raises `confidence` / `support_count`. This is why the memory does not rot.
3. **A contradicted fact is never deleted.** It is marked `superseded` and linked to
   its successor with a `supersedes` relation. History stays auditable, and the
   assistant can say *"you used to tell me X, now it's Y"*.
4. **Salience is computed, not chronological.**
   `score = importance × recency × relevance × confidence`, where `recency` is a
   half-life decay whose period depends on the fact's category — a stated goal decays
   over a year, a transient mood over two weeks.
5. **A closed vocabulary of predicates and categories.** Without it, LLM extraction
   produces a thousand synonymous predicates and matching becomes impossible.

EMEFA's current memory violates all five. This is the user's explicitly stated
priority and is implemented first.

**Not taken:** the Markdown mirror (Obsidian vault on the local filesystem). EMEFA is
a hosted product; the equivalent user-facing surface is the memory panel plus an
export endpoint.

### 2.2 Autonomy levels

jarvis-OS grades every proactive act 0–5 and hard-codes one rule: **level 5
(publish / pay / contact / delete) always requires human validation, whatever the
configuration says.** EMEFA already has risk classes; what it lacks is the *initiative*
object that carries a goal, a budget and a deadline through time. Both are needed —
risk classifies an action, autonomy classifies a decision to act unprompted.

### 2.3 Skills as data, not code

`jarvis-skills` (MIT) defines a manifest EMEFA can adopt verbatim:
`name`, `version`, `author`, `description`, `tags`, `type`, `platforms`,
`requires_env`, `requires_tools`, `requires_oauth`, `requires_apps`, `capabilities`,
validated by a JSON schema, indexed in `index.json`. A conversational skill is a
`SYSTEM_PROMPT` plus optional tools.

EMEFA adopts the manifest and the index format so the existing catalogue stays
loadable, and adds what a hosted product requires and the standard does not have:
per-assistant enablement, risk class per skill, credential isolation, and the
prohibition on executing arbitrary contributed Python (CLAUDE.md §18, §48).

**Deliberate divergence:** jarvis-OS installs skills as Python files executed in the
host process (`skills_data/installed/*/skill.py`). EMEFA will **not** do that. A
contributed skill contributes a prompt, a manifest and declarative tool bindings to
tools EMEFA already ships. Arbitrary code execution from a marketplace is exactly the
shortcut CLAUDE.md §48 forbids.

### 2.4 Budget guard

Per-scope spend accounting with thresholds and a hard stop. EMEFA currently has no
idea what a conversation costs. CLAUDE.md §15 requires this; jarvis-OS has a working
shape for it (`scope → spent/limit → status`, seeded from history at boot).

---

## 3. Biometric identification — scope reduction, stated plainly

jarvis-OS's "Wake Up" sequence runs `face_recognition` (dlib) on the **host's**
webcam against one reference photo, and gates nothing — it is a greeting, not a
security control. Two things follow for EMEFA:

- Porting dlib/YOLO into EMEFA's backend adds heavy native dependencies for a feature
  that grants no authorisation. Rejected.
- The *experience* — EMEFA recognising who woke her and greeting them by name — is
  worth keeping, and EMEFA can deliver it from what it already has: the authenticated
  session identifies the user; the holographic face plays the recognition sequence.

So: identification is **cryptographic**, presentation is **cinematic**. If real face
matching is wanted later it belongs client-side (MediaPipe in the browser, already a
dependency of the face work) as a *convenience* unlock over an existing session, never
as the primary credential. That would be a separate ADR.

---

## 4. Licence — the one decision that cannot be undone

| Repository | Licence | What that means for EMEFA |
|---|---|---|
| `jarvis-OS` | **AGPL-3.0-or-later** | Copying or adapting its source makes EMEFA a derivative work: EMEFA must be released under AGPL-3.0, **and** §13 obliges you to offer complete source to every user who reaches EMEFA over a network — i.e. all of them |
| `jarvis-skills` | **MIT** | Reusable, including commercially, provided the copyright notice and licence text are preserved |

EMEFA has no `LICENSE` file, so it is proprietary by default, and it is being built as
a commercial product for entrepreneurs and SMEs.

**Decision (ADR-004): re-implement, do not copy.** Architecture, algorithms and
database designs are not protected by copyright; source code is. Every subsystem is
written fresh in EMEFA's own idiom, against EMEFA's own schema and multi-tenant
scoping. No file, function body or comment is transcribed from jarvis-OS. Design
credit is recorded in `docs/CREDITS.md`.

This path is also safe under the *opposite* choice: if EMEFA is later published under
AGPL deliberately, nothing needs to be undone.

MIT content from `jarvis-skills` that is reused (manifest schema, skill prompts,
catalogue index) carries its notice in `backend/emefa/skills/catalog/NOTICE`.

---

## 5. Implementation order

Ordered by the user's stated priorities, then by dependency.

| Slice | Content | Depends on |
|---|---|---|
| **1** | Gap analysis + ADR-002 (identity), ADR-003 (memory), ADR-004 (licence) | — |
| **2** | Memory Kernel: schema, kernel, retrieval, migration of existing `memories` | 1 |
| **3** | Fact ingestion + reconciliation + nightly consolidation | 2 |
| **4** | Real accounts: owner account, password hashing, login, per-user scoping | 1 |
| **5** | Skills registry + jarvis-skills manifest compatibility + catalogue import | 1 |
| **6** | Event bus + budget guard + usage tracking | 1 |
| **7** | Proactive engine: initiatives, autonomy 0–5, collectors, command center, curator | 3, 6 |
| **8** | Mission engine: plan/execute/verify/resume | 6 |
| **9** | HUD / views to match the reference layout | 7 |

Voice stays exactly as it is. The holographic face stays exactly as it is.

---

## 6. Credits

EMEFA's memory, proactive-governance and skills-registry designs are informed by
**Jarvis OS** by Barthélemy Houot (AGPL-3.0) and its companion catalogue
**jarvis-skills** (MIT). EMEFA's implementations are original; the debt is one of
design, and it is acknowledged here and in `docs/CREDITS.md`.
