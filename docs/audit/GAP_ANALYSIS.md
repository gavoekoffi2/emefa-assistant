# EMEFA — Gap Analysis (Phase 0)

> **Date:** 2026-07-20 · Classification of every major target capability (specs in `docs/`) against verified current state (commit `6fa6f62`).
> Statuses: `READY` · `PARTIAL` · `MISSING` · `UNSAFE` · `DEFERRED` (per `CLAUDE_EXECUTION_PROMPT.md` §12).

| Target capability | Status | Evidence / gap | Recommended next action |
|---|---|---|---|
| Private access / device auth | PARTIAL | Works (enrollment code, hashed tokens, strict cookies) but no rate limiting (S1), no token expiry (S2), single shared code | Phase 1: rate-limit + lockout, server-side expiry; real user accounts deferred to platformization |
| Identity: tenant / user / assistant model | MISSING | Only `Device` exists; nothing to attach memory, skills, or workflows to | Phase 1: introduce minimal `tenant_id`/`user_id`/`assistant_id` schema (single-tenant instance, tenant-ready shape) — ADR required |
| Realtime voice (French, barge-in, transcripts) | READY (provider-owned) | Fully working via ElevenLabs Agents; signed-URL brokerage is sound | KEEP as production path. Do not remove (CLAUDE.md §12). Plan provider abstraction before any migration |
| Voice governed by EMEFA runtime | MISSING / architectural risk | Voice brain is the ElevenLabs dashboard agent; backend policy/memory/tools cannot apply; persona config lives outside git | Phase 3 decision (ADR): route reasoning through EMEFA backend (e.g. ElevenLabs custom-LLM/webhook mode or LiveKit pipeline) after benchmark; until then, version the agent persona in-repo |
| Text conversation sharing voice context | PARTIAL | Typed input exists but only injects into the ElevenLabs session; `/v1/agent/runs` orphaned; no shared history | Phase 3: single Session Orchestrator serving both modalities |
| Bounded orchestration | PARTIAL | `AgentEngine` (turn budget, risk gate, typed contracts) is sound but unused and tool-less | KEEP + wire into product; implement structured tool-calling in `DeepSeekBrain` (currently discards tools) |
| Risk policy / autonomy levels | PARTIAL | Deterministic 7-class → RUN/ASK/BLOCK exists with tests; no approval persistence, no approval UI, no scoped/persistent approvals | Extend when first consequential skill ships (Phase 5); build approval inbox at that point |
| Memory & personalization | MISSING | No storage, retrieval, provenance, or user control; in-process 12-turn buffer only | Phase 4 per roadmap; structured DB first, no vector store yet |
| Conversational onboarding / business profile / ICP | MISSING | No onboarding flow or profile entities | Phase 2 |
| Skills registry / tool gateway | MISSING (seed exists) | `ToolShelf` registry pattern is the right seed; zero skills registered | Phase 5: grow ToolShelf into registry w/ schemas, permissions, audit; wrap first native skills |
| MCP integration | MISSING | No MCP code | DEFERRED until a selected MVP integration needs it (roadmap §41) |
| External agent gateway (Agent Zero) | MISSING | — | DEFERRED (roadmap §42: optional for MVP) |
| Document generation (OfficeCLI etc.) | MISSING | — | Phase 6/7; spike doc `docs/spikes/OFFICECLI_EVALUATION.md` before adoption |
| Email / calendar / meeting prep | MISSING | — | Phase 6 vertical slices |
| Business development / prospecting | MISSING | — | Phase 7 |
| Durable workflows / scheduling / approval inbox | MISSING | No workers, queues, or schedules | Phase 8; needs persistence layer first |
| Audit trail | MISSING | No audit events anywhere | Start minimal in Phase 1 (auth + agent events) — cheap now, expensive to retrofit |
| Observability | MISSING | No structured logs, correlation IDs, cost/latency tracking | Phase 1 baseline: structured logging + request IDs |
| Multi-tenancy | MISSING | Single-instance, single shared code | Architecture-ready IDs in Phase 1; real multi-tenant = Phase 12 (platformization) |
| African languages (Ewe, Kabiye…) | MISSING | UI hard-coded French; provider languages unverified | DEFERRED; keep provider abstraction extensible (Phase 11) |
| PWA / mobile / low bandwidth | PARTIAL | Manifest + SW + mobile CSS exist; 1.2 MB bundle; no offline strategy beyond shell | Phase 1/9: code-split three.js; measure on mobile |
| 3D immersive identity | READY | Distinctive, state-reactive, reduced-motion aware | PRESERVE; later connect HUD data to real state (currently partly decorative) |
| Tests / CI | PARTIAL | 27 backend tests good; web tests are regex-based; **no CI pipeline** | Phase 1: add GitHub Actions running the 4 existing check commands |
| Deployment | READY (single-node) | Docker + Traefik + volume; runbook accurate | KEEP; complete `.env.example` (was partial) |

## Subsystem decisions (audit vocabulary from CLAUDE.md §5)

| Subsystem | Decision |
|---|---|
| Frontend shell + holographic UI | **KEEP + HARDEN** (code-split, real telemetry, component tests) |
| ElevenLabs voice path | **KEEP** now; **MIGRATE-candidate** later behind adapters after benchmark (UNKNOWN/REQUIRES BENCHMARK for LiveKit) |
| Backend app factory / auth / session | **KEEP + HARDEN** (rate limit, expiry, audit, logging) |
| AgentEngine + policy + ToolShelf | **KEEP + EXTEND** (wire to product, add tool-calling) |
| DeepSeek brain | **KEEP** as economical default behind existing `Brain` protocol (already provider-abstracted) |
| SQLite persistence | **KEEP** for single-instance MVP; add migration discipline; revisit at platformization (ADR) |
| In-process conversation state | **REFACTOR** to persistent storage when memory phase starts |
| Android prototype | **KEEP frozen** (archive), exclude from all work |
| Unused OpenAI realtime settings | **REMOVE** (dead config) when touching `config.py` |

## Immediate critical fixes (Phase 1 candidates, priority order)

1. `.env.example` + accurate root README run instructions (handoff contract, TD-1).
2. Rate limiting/lockout on activation & enrollment (S1).
3. Server-side session expiry using existing `created_at` (S2).
4. Structured logging + request correlation IDs + minimal audit events (S4/TD-7).
5. Minimal identity schema (tenant/user/assistant) behind current device auth (TD-5) — ADR-001.
6. CI pipeline running existing checks.

No rewrite of any existing subsystem is justified by evidence. The existing voice product and UI must be preserved as-is while foundations are added around them.
