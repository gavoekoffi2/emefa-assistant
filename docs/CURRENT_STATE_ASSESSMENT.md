# EMEFA — CURRENT_STATE_ASSESSMENT.md

> **Document type:** Completed brownfield repository audit (fills the mandatory template shipped with the spec pack)
> **Repository:** `gavoekoffi2/emefa-assistant` · **Commit audited:** `6fa6f62` · **Date:** 2026-07-20 · **Executor:** Claude
> **Detail documents:** `docs/audit/REPOSITORY_AUDIT.md` (findings & debt register), `docs/audit/CURRENT_ARCHITECTURE.md` (verified diagrams & flows), `docs/audit/GAP_ANALYSIS.md` (capability deltas & decisions).
> Every statement below comes from direct inspection; checks were actually executed and results recorded.

---

## 1. Executive Summary

### Overall assessment

The repository contains a **small, clean, working V1 of a private French voice assistant** (~2,000 lines of product code), not yet the platform the specifications describe. What exists is genuinely good: an interruptible realtime voice conversation, a distinctive JARVIS-style holographic 3D interface, disciplined server-side secret handling, a typed bounded agent skeleton with a deterministic risk policy, full passing test/lint/build baselines, and a reproducible single-node Docker/Traefik deployment (live on a VPS).

The documented baseline in the spec pack **overstates** current state in places: there is no memory system, no audit foundations, no tools in use, no multi-tenancy, and no PWA beyond a shell manifest/service worker. `android/` is an explicitly frozen prototype.

**Strongest engineering decisions:** server-brokered ElevenLabs signed URLs (no client secrets); `Brain` protocol + `ToolShelf` + `decide()` policy as correct seams for the future skills architecture; hashed device tokens with strict cookies; state-reactive 3D rendering with reduced-motion and mobile budgets.

**Largest architectural fact:** the product currently has **two disconnected brains**. The voice users actually experience is an ElevenLabs-hosted agent whose persona/model live in the provider dashboard (outside git). The governed backend path (`/v1/agent/runs` → DeepSeek → policy → tools) is never called by the frontend, and its `ToolShelf` is empty. Every capability the specs require (memory, skills, approvals, audit) can only be enforced in the backend path — so reconnecting these paths is the central architectural task ahead. ElevenLabs lock-in: **HIGH** (brain + voice pipeline), mitigated by the fact that the integration surface in our code is tiny (one gateway class, one SDK hook).

**Largest risks:** brute-forceable single activation code (no rate limiting — HIGH); non-expiring device tokens (MEDIUM); ungoverned provider-side persona (MEDIUM); zero observability/audit (LOW today, expensive to retrofit).

**Readiness:** excellent for continued development. Nothing is broken; all checks pass; no rewrite of any subsystem is justified by evidence.

### Recommended immediate direction (Phase 1)

1. `.env.example` + accurate quickstart (handoff contract).
2. Rate limiting/lockout on activation and enrollment endpoints.
3. Server-side session expiry (reuse stored `created_at`).
4. Structured logging + request IDs + minimal audit events.
5. ADR-001: minimal tenant/user/assistant identity model (single-tenant instance, tenant-ready shape).
6. CI running the four existing check commands.

---

## 2. Repository Snapshot

```text
Repository:      gavoekoffi2/emefa-assistant
Branch:          claude/emefa-phase-0-audit-2pqf2i (from main @ 6fa6f62)
History:         2 commits (implementation, then spec pack)
Node:            22-alpine (build) · npm lockfile v3
Python:          >=3.11 (audited on 3.11.15)
Package mgrs:    pip (pyproject.toml) · npm
Database:        SQLite, single `devices` table
Frontend:        React 19 + TypeScript ~6.0 + Vite 8 + three 0.185 + @elevenlabs/react 1.10
Backend:         FastAPI ≥0.115 + uvicorn + pydantic-settings + httpx
Deployment:      Docker multi-stage → single container behind Traefik (TLS), volume-backed SQLite
                 Live: https://emefa.76.13.129.252.sslip.io
Working tree:    clean at audit start
```

## 3. Repository Map

See `docs/audit/REPOSITORY_AUDIT.md` §2 for the full annotated table. Summary:

- `backend/emefa/` — FastAPI app factory (`main.py`), settings, three API routers (devices/web-session, agent, realtime), domain (`agent.py`, `policy.py`, `devices.py`), infrastructure adapters (`deepseek.py`, `realtime.py`). All active production code.
- `backend/tests/` — 9 files, 27 tests, mock-transport based. Passing.
- `web/src/` — 3 components (`App`, `VoiceRoom`, `HolographicUniverse`) + CSS. Active. `KnowledgeGalaxy` (2D canvas) is exported but unmounted (superseded).
- `web/public/` — PWA manifest, service worker, ElevenLabs audio worklets.
- `android/` — frozen pre-product prototype; archive only.
- `docs/` — 15 spec documents (direction), ops runbook (`DEPLOIEMENT.md`), now audit deliverables.
- Root — `Dockerfile`, `docker-compose.prod.yml`, spec/constitution files.

Dead/legacy: `android/`, Vite template leftovers (`web/README.md`, sample assets), unused OpenAI-realtime settings in `config.py`.

## 4. Frontend

- **Framework:** React 19 functional components + hooks; Vite 8; TypeScript strict via `tsc -b`; oxlint.
- **Routing/state:** none/none — single view switched on session presence; local `useState` only. Appropriate at current size.
- **API layer:** small typed `fetch` wrapper with `credentials: 'include'` and French error surfaces.
- **Realtime client:** `@elevenlabs/react` `useConversation` (WebSocket + audio worklets), real barge-in, mode/status callbacks drive a 5-state machine (`idle/listening/thinking/speaking/error`).
- **Voice UI / 3D:** `HolographicUniverse` (three.js WebGL): state-colored reactive core, rings, particles, node graph; pixel ratio capped at 1.6; 320-particle mobile budget; `prefers-reduced-motion` honored; proper disposal on unmount. HUD includes some **decorative** data (fake percentages, random node activation) — conflicts with the "honest state" principle; fix later, don't remove the identity.
- **PWA/mobile:** manifest + minimal shell-cache service worker (PROD only); mobile CSS breakpoint. Bundle is 1.2 MB minified (three.js not split) — a real concern for the low-bandwidth target market.
- **Accessibility:** aria-labels on canvases/orb/inputs, `role="alert"` for errors, labeled form fields, reduced-motion. No keyboard-trap issues observed at this size; no formal a11y pass yet.
- **Tests:** 4 node-test cases asserting regexes over source files — protect intent, not behavior.
- **Overall classification: KEEP + HARDEN.**

## 5. Backend

- **Framework:** FastAPI app factory with constructor injection (settings/brain overridable — used by tests); lifespan closes provider clients.
- **APIs:** `/health`; `/v1/devices/{enroll,me}`; `/v1/web/session` (POST/GET/DELETE); `/v1/agent/runs`; `/v1/realtime/session`. All `/v1` routes device-authenticated except enrollment/activation. Pydantic-validated bodies; normalized error details; `no-store` on API responses; security headers + CSP middleware.
- **Orchestration:** `AgentEngine` — bounded loop (max 4 turns), per-device rolling 12-turn in-process history, risk-policy gate producing `completed / confirmation_required / blocked / failed`. Sound contract; currently unused by the UI; no callers implement the confirmation flow.
- **Tools:** `ToolShelf` registry (name/description/risk/handler) — empty; `DeepSeekBrain` discards tool descriptions, so tool steps are unreachable in practice.
- **Persistence:** SQLite via stdlib `sqlite3`, parameterized queries; single table; `CREATE TABLE IF NOT EXISTS` only — no migration mechanism.
- **Background jobs / realtime endpoints:** none — voice audio bypasses the backend entirely (provider WebSocket).
- **Coupling:** low and healthy — providers behind `Brain`/`RealtimeGateway` seams; domain has no FastAPI imports.
- **Overall classification: KEEP + HARDEN.**

## 6. Voice (exact verified pipeline)

```text
Microphone (echoCancellation/noiseSuppression/autoGainControl; permission stream immediately stopped)
→ GET /v1/realtime/session  (cookie-authenticated; 503 if unconfigured; 502 on provider errors)
→ backend RealtimeGateway → ElevenLabs get-signed-url (xi-api-key server-side only)
→ browser opens provider WebSocket directly (signed URL)
→ ElevenLabs Agents platform: VAD + turn detection + STT + agent LLM (dashboard persona) + TTS + barge-in
→ audio out via worklets; transcripts via onMessage → HUD state machine → hologram color/motion
```

Explicit answers (template §8.2): ElevenLabs does STT **yes**, hosts the conversational agent **yes**, does TTS **yes**. System prompt: **ElevenLabs dashboard, not in repo**. EMEFA orchestration in voice path: **none**. Tools invoked: **never**. Interruption: **provider-native, working**. Transcript propagation: SDK `onMessage` → local state (kept to last 8 turns, not persisted). Session lifecycle: SDK `startSession`/`endSession`; state derived from `status`/`isSpeaking`/`onModeChange`. Credentials: API key server-only; browser gets ephemeral signed URL. Client/server split: **correct**. Latency risk: single provider RTT, unmeasured — baseline benchmark required before migration talk. **Vendor coupling: HIGH** (see lock-in note in §1); integration surface in code is small (1 class + 1 hook), which keeps migration feasible.

## 7. Data

- **Database:** SQLite file (Docker volume in prod). Entity: `devices(device_id PK, name, token_hash UNIQUE, created_at)`. Owner: instance (no tenant scoping — single-tenant by construction). Sensitive: `token_hash` (SHA-256 of urlsafe-32 token).
- **Migrations:** none. **Tenant model:** none. **Memory model:** none durable (in-process conversation dict; provider-side voice session). **Audit model:** none.
- **Browser persistence:** session cookie + PWA shell cache. **Vector/object stores, caches, queues:** none.

## 8. Integrations Inventory

| Provider | Use | Where | Credential |
|---|---|---|---|
| ElevenLabs Agents | Full voice pipeline + conversation brain | `infrastructure/realtime.py`, `@elevenlabs/react` | `EMEFA_ELEVENLABS_API_KEY` (server) + `EMEFA_ELEVENLABS_AGENT_ID` |
| DeepSeek | Text brain for orphaned `/v1/agent/runs` | `infrastructure/deepseek.py` | `EMEFA_DEEPSEEK_API_KEY` (server) |
| Traefik / Docker | TLS, routing, runtime | `docker-compose.prod.yml` | — |

No MCP servers, CLIs, external agents, or other cloud services. `EMEFA_OPENAI_API_KEY` / `EMEFA_REALTIME_MODEL` / `EMEFA_REALTIME_VOICE` are read into `Settings` but used nowhere — dead config from an earlier direction.

## 9. Security

Verified strengths: secrets server-side only (`SecretStr`, never logged/echoed); no secrets in repo or git history; constant-time code comparison; hashed tokens; httpOnly/secure/SameSite=strict cookie; device cap; security headers + restrictive CSP; parameterized SQL; non-root container; input validation via Pydantic (length-bounded).

Findings (full table: `REPOSITORY_AUDIT.md` §8): **S1 HIGH** no rate limiting on code-guarded endpoints → online brute force of the shared activation code; **S2 MEDIUM** tokens never expire server-side; **S3 MEDIUM** voice persona/policy is provider-dashboard state, ungoverned by repo policy code; **S4 LOW** no audit/observability; **S5 LOW** `--forwarded-allow-ips "*"` acceptable only behind Traefik-only networking; **S6 INFO** no CORS layer (same-origin correct today).

Prompt-injection exposure: currently limited — no tools execute, no retrieved content enters context; the DeepSeek system prompt explicitly forbids claiming performed actions and revealing secrets. The exposure will appear the moment tools/memory ship; trust boundaries must be designed then (specs `SECURITY.md` §15–17).

## 10. Quality

- **Backend tests:** 27 passing (`pytest -q`, 1.42 s) covering health, auth/enrollment limits, cookies, agent statuses incl. confirmation/block paths, engine turn budget, DeepSeek adapter via mock transport, realtime brokerage incl. provider-failure mapping, static-web production wiring. Good coverage of what exists.
- **Web:** oxlint clean; 4 regex-based tests pass; `tsc -b && vite build` passes with chunk-size warning.
- **CI:** none (`.github/workflows` absent). **Evaluations:** none. **Observability:** none.

## 11. Decision Table (mandated vocabulary)

| Subsystem | Decision | Reason |
|---|---|---|
| Frontend shell + 3D holographic UI | **KEEP + HARDEN** | Distinctive working identity; needs code-split, honest telemetry, behavioral tests |
| Voice path (ElevenLabs) | **KEEP** now; **UNKNOWN / REQUIRES BENCHMARK** for future transport (LiveKit) / custom-LLM routing | Working product value; CLAUDE.md §12 forbids removal before validated replacement; no baseline measurements exist yet |
| Backend app/auth/session | **KEEP + HARDEN** | Sound structure; needs S1/S2 fixes, logging, audit |
| AgentEngine + policy + ToolShelf | **KEEP** (+ extend & wire into product) | Correct seams; unused today |
| DeepSeek brain | **KEEP** | Economical default already behind `Brain` protocol |
| SQLite + persistence | **KEEP + HARDEN** (migration discipline) | Right size for single-instance MVP; revisit at platformization via ADR |
| In-process conversation state | **REFACTOR** (persist) | Lost on restart; wrong under multiple workers |
| Decorative HUD data | **REFACTOR** | Violates honest-state principle; keep the visuals |
| Unused OpenAI realtime config | **REMOVE** | Dead code |
| Android prototype | **KEEP (frozen archive)** | Declared non-product |
| Regex web tests | **REFACTOR** to behavioral tests | Low assurance for the most valuable UI |

## 12. What Must Be Preserved / Hardened / Not Touched Yet

- **Preserve:** holographic UI identity; interruptible French voice UX; signed-URL brokerage pattern; typed agent contracts; deterministic risk policy; deployment runbook accuracy.
- **Harden:** activation endpoints (S1/S2), logging/audit, migration discipline, CI, bundle size, web test quality.
- **Do NOT touch yet (benchmark/approval first):** voice provider migration or LiveKit adoption (needs measured baseline + ADR); database replacement; any UI redesign; multi-tenant productization; MCP/Agent Zero integration.

## 13. Decisions Required From Product Owner

1. **ElevenLabs agent governance:** export the dashboard persona/config into the repo (or grant API access so Claude can) — prerequisite for versioning the product's actual voice behavior. Recommended: yes, soon.
2. **Voice reasoning routing (later, ADR):** when Phase 3 arrives, choose between ElevenLabs custom-LLM/webhook mode vs LiveKit pipeline so the EMEFA runtime owns the brain. Requires the baseline benchmark first; no action needed now.
3. Nothing else blocks Phases 1–2; remaining choices are reversible engineering decisions Claude will document as ADRs.

## 14. Risk Register (top)

| Risk | Prob. | Impact | Mitigation |
|---|---|---|---|
| Activation code brute force (S1) | Med | High | Phase 1 rate limiting/lockout |
| Provider lock-in deepens as features attach to ElevenLabs brain | High | High | Freeze feature growth on provider agent; build features on EMEFA runtime; version persona in repo |
| Retrofitting audit/observability later | High | Med | Minimal structured logging + audit events in Phase 1 |
| 1.2 MB bundle on low-bandwidth mobile | High | Med | Code-split three.js; measure |
| Voice cost/latency unknown (no baseline) | Med | Med | Benchmark before any migration decision |
| Spec/implementation drift (docs describe non-existent baseline) | — | Med | This assessment + audit docs are now authoritative for current state |

## 15. Recommended First Vertical Slice (after Phase 1)

**Assistant identity & conversational onboarding persisting a business profile** (roadmap Phase 2): it is demonstrable, exercises the identity model and persistence added in Phase 1, feeds every later capability (memory, briefs, prospecting), and requires no new providers. Voice/text convergence (Phase 3) and the morning-brief slice follow.

---

*Understand before changing. Preserve before replacing. Measure before migrating. Verify before declaring success.*
