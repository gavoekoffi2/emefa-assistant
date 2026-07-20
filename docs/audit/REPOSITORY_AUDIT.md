# EMEFA — Repository Audit (Phase 0)

> **Date:** 2026-07-20
> **Branch:** `claude/emefa-phase-0-audit-2pqf2i` (from `main` @ `6fa6f62`)
> **Auditor:** Claude (brownfield continuation agent)
> **Method:** Full source inspection of every file in `backend/`, `web/`, `android/`, deployment configuration, plus execution of all available non-destructive checks.

---

## 1. Verified Snapshot

```text
Repository:      gavoekoffi2/emefa-assistant
Commit audited:  6fa6f62 (docs: prepare EMEFA specification and Claude handoff)
History:         2 commits — ee1494c "Initial commit: greenfield EMEFA voice assistant", 6fa6f62 (specs only)
Node:            22 (Docker build), npm lockfile v3
Python:          >=3.11 required; 3.11.15 used for audit
Backend:         FastAPI >=0.115, uvicorn, pydantic-settings, httpx
Frontend:        React 19, Vite 8, TypeScript ~6.0, three ^0.185, @elevenlabs/react ^1.10
Database:        SQLite (single `devices` table), path via EMEFA_DATABASE_PATH
Deployment:      Docker multi-stage + docker-compose + Traefik; live at emefa.76.13.129.252.sslip.io
```

The entire product implementation is **~2,000 lines of code** (backend + frontend + tests). The specification pack (~25,000 lines in `docs/` + root) describes a far larger target platform. The repository is the source of truth for current state; the specs are direction.

## 2. Repository Map

| Path | Responsibility | Status |
|---|---|---|
| `backend/emefa/main.py` | App factory, DI wiring, security headers/CSP middleware, `/health`, static hosting of `web/dist` | Active, production |
| `backend/emefa/config.py` | `Settings` (pydantic-settings, `EMEFA_` prefix, `.env`) | Active |
| `backend/emefa/api/devices.py` | Device enrollment (`/v1/devices/*`), bearer/cookie auth dependency `current_device` | Active |
| `backend/emefa/api/web_session.py` | Browser activation via enrollment code → httpOnly cookie (`/v1/web/session`) | Active |
| `backend/emefa/api/agent.py` | `/v1/agent/runs` — authenticated text agent endpoint | Active but **unused by the frontend** |
| `backend/emefa/api/realtime.py` | `/v1/realtime/session` — brokers ElevenLabs signed URL after device auth | Active, core of voice path |
| `backend/emefa/domain/agent.py` | `AgentEngine` bounded loop (max 4 turns), `ToolShelf` registry, `AgentStep`/`AgentReply` contracts | Active; **ToolShelf is empty** — no tool is ever registered |
| `backend/emefa/domain/policy.py` | `ActionRisk` (7 classes) → `Decision` (RUN/ASK/BLOCK), deterministic | Active |
| `backend/emefa/domain/devices.py` | SQLite `DeviceRepository`, SHA-256 token hashing | Active |
| `backend/emefa/infrastructure/deepseek.py` | `DeepSeekBrain` chat adapter; French system prompt; **ignores tools** (`del tools`) | Active when `EMEFA_DEEPSEEK_API_KEY` set |
| `backend/emefa/infrastructure/realtime.py` | `RealtimeGateway` — server-only ElevenLabs signed-URL client | Active |
| `backend/tests/` (9 files, 27 tests) | API, engine, policy, device, gateway coverage with mock transports | Passing |
| `web/src/App.tsx` | Activation flow, session check, 2D canvas `KnowledgeGalaxy`, `VoiceOrb`, shared types | Active |
| `web/src/VoiceRoom.tsx` | ElevenLabs `useConversation` session, state machine, HUD, typed command dock | Active, core UX |
| `web/src/HolographicUniverse.tsx` | three.js WebGL scene: reactive core, rings, particle field, node graph; state-colored; reduced-motion aware | Active, distinctive identity |
| `web/src/*.css` | JARVIS-style HUD styling; `prefers-reduced-motion`; mobile breakpoint | Active |
| `web/public/` | PWA manifest, service worker, ElevenLabs audio worklets | Active |
| `web/tests/realtime-ui.test.js` | 4 static-content contract tests (regex over source) | Passing, low assurance |
| `android/` | Frozen pre-product prototype; README declares it archive-only | Legacy, non-shipped |
| `Dockerfile`, `docker-compose.prod.yml`, `docs/DEPLOIEMENT.md` | Multi-stage build, Traefik TLS routing, ops runbook (French) | Active |
| `docs/*.md` (15 specs) | Target specifications; `CURRENT_STATE_ASSESSMENT.md` was an unfilled template before this audit | Direction |

Dead/legacy code: `android/` (explicitly frozen), `web/src/assets/react.svg`/`vite.svg` (template leftovers), `web/README.md` (Vite template boilerplate). `App.tsx` exports a 2D `KnowledgeGalaxy` canvas that `VoiceRoom` no longer renders (superseded by `HolographicUniverse`) — only referenced by its own export and `graphNodes` reuse.

## 3. Verified Check Results

```text
Backend:  pip install -e ".[test]"      → OK
          python -m pytest -q           → 27 passed in 1.42s
Frontend: npm ci                        → OK (no vulnerabilities reported)
          npm run lint (oxlint)         → 0 warnings/errors
          npm test (node --test)        → 4/4 pass
          npm run build (tsc -b + vite) → OK; warning: main chunk 1,202 kB minified
                                          (319 kB gzip) — three.js dominates
```

The application starts and serves without any secret configured (voice returns 503 `realtime_not_configured`; agent replies "not configured" text). No blockers to local development. `.env.example` **does not exist** — required env vars are only documented in `docs/DEPLOIEMENT.md`.

## 4. Working Features (evidence-based)

1. **Private activation** — enrollment code (`secrets.compare_digest`) → device row + urlsafe token (hash stored) → httpOnly/secure/SameSite=strict cookie; max 3 devices; revocation via `DELETE /v1/web/session`.
2. **Realtime voice conversation** — browser mic → ElevenLabs Conversational AI via `@elevenlabs/react` over a server-brokered signed URL. Provider handles VAD, STT, LLM turn, TTS, and barge-in. UI reflects `listening/thinking/speaking/error` from real SDK callbacks (`onModeChange`, `status`, `isSpeaking`).
3. **Typed input into the live voice session** (`sendUserMessage`/`sendUserActivity`).
4. **Immersive 3D identity** — state-reactive WebGL hologram (color/motion per state), HUD telemetry, French JARVIS-style presentation; `prefers-reduced-motion` honored; pixel-ratio capped; mobile particle budget.
5. **Bounded text agent skeleton** — `/v1/agent/runs` runs DeepSeek with per-device conversation memory (last 12 turns, in-process dict), 4-turn budget, risk-policy gate that blocks MONEY/SYSTEM_CHANGE and asks for COMMUNICATE/DESTRUCTIVE.
6. **Deployment** — reproducible Docker build, non-root user, Traefik TLS, persistent volume for SQLite, documented runbook.

## 5. Partially Working / Latent

- **Agent engine ↔ product disconnect (key finding):** the frontend never calls `/v1/agent/runs`. The visible "brain" in every conversation is the ElevenLabs-hosted agent (its system prompt and model configured in the ElevenLabs dashboard, **not in this repository**). The DeepSeek engine, tool policy, and risk model currently govern nothing the user touches.
- **ToolShelf** is a working registry with zero registered tools; `DeepSeekBrain.think()` explicitly discards tool descriptions, so no tool call can ever be produced.
- **Conversation memory** is in-process only (lost on restart, wrong under multiple workers).
- **`KnowledgeGalaxy` 2D canvas** exported but unmounted; graph data is decorative (random node activation on assistant replies, hard-coded "16 sources synchronisées").
- **Web tests** assert source-code regexes, not behavior.

## 6. Broken Features

None found. Everything present functions as coded. The gap is scope, not breakage.

## 7. Voice Stack (exact, verified)

```text
Microphone (browser, echoCancellation/noiseSuppression/autoGainControl)
→ @elevenlabs/react useConversation.startSession({ signedUrl, workletPaths })
→ WebSocket wss://api.elevenlabs.io (signed URL from GET /v1/realtime/session, device-authenticated)
→ ElevenLabs Agents platform: VAD + turn detection + STT + agent LLM + TTS + barge-in
→ streamed audio ← audio worklets (web/public/worklets/*)
→ transcripts via onMessage → HUD state/history
```

Answers to the assessment's mandatory questions: ElevenLabs handles **STT, the conversational agent, and TTS**. The voice system prompt lives **in the ElevenLabs dashboard** (outside the repo). EMEFA orchestration (`AgentEngine`) executes **nowhere in the voice path**. Tools are **not invoked at all**. Interruption is **provider-native**. Session state is per-connection at the provider. Credentials: API key server-side only; browser receives a short-lived signed URL. Lock-in classification: **HIGH** (conversation brain, persona, and voice pipeline all provider-hosted; only session brokerage is ours).

## 8. Security Findings

| # | Severity | Finding | Evidence |
|---|---|---|---|
| S1 | HIGH | No rate limiting / lockout on `POST /v1/web/session` and `/v1/devices/enroll` — the single shared enrollment code can be brute-forced online. Constant-time compare prevents timing leaks but not volume attacks. | `api/web_session.py:31`, `api/devices.py:54` |
| S2 | MEDIUM | Device tokens never expire server-side. Cookie `max_age` is 30 days, but the underlying token remains valid forever (until manual revocation); a leaked token is permanent. `created_at` is stored but unused. | `domain/devices.py`, `config.py:14` |
| S3 | MEDIUM | Voice-agent policy is not governed by the repo: the ElevenLabs agent's prompt/permissions are dashboard state, so `domain/policy.py` protections do not apply to the primary user path. | `infrastructure/realtime.py`, absence of agent config |
| S4 | LOW | No audit log of authentication, enrollment, or agent actions; no structured logging, no correlation IDs anywhere. | whole backend |
| S5 | LOW | `docker-compose.prod.yml` runs uvicorn with `--forwarded-allow-ips "*"`; acceptable only while the container is exclusively behind Traefik on an internal network. | `Dockerfile` CMD |
| S6 | INFO | No CORS middleware (same-origin only — correct for current single-origin serving). CSP allows only self + ElevenLabs endpoints — good. Secrets handled via `SecretStr`, never logged, never sent to client — good. No secrets found in repo or git history. | `main.py:70-86` |

Positive controls worth preserving: server-side credential brokerage, hashed tokens, `compare_digest`, strict cookies, security headers/CSP, device cap, non-root container.

## 9. Technical Debt Register

| ID | P | Item | Impact |
|---|---|---|---|
| TD-1 | P0 | No `.env.example`; setup knowledge lives only in the ops runbook | Handoff/reproducibility (contract requirement) |
| TD-2 | P0 | S1 rate limiting (see above) | Security |
| TD-3 | P1 | Two disconnected brains (ElevenLabs agent vs DeepSeek engine); no shared context between voice and `/v1/agent` | Architecture dead-end for memory/skills; HIGH vendor lock-in |
| TD-4 | P1 | S2 token expiry | Security |
| TD-5 | P1 | No identity model beyond `device` (no tenant/user/assistant); all future memory/skills have nothing to attach to | Blocks Phases 2+ |
| TD-6 | P1 | In-process conversation state; no persistence beyond `devices` table; no migration mechanism | Reliability, future data work |
| TD-7 | P2 | No observability (no structured logs, request IDs, cost/latency capture) | Operations |
| TD-8 | P2 | Web tests are source regexes; no component/E2E tests | Regression risk on the valuable UI |
| TD-9 | P2 | 1.2 MB main bundle (three.js not code-split); PWA precache list in `sw.js` is minimal | Mobile/low-bandwidth targets |
| TD-10 | P3 | Decorative HUD data (fake telemetry percentages, fake node activation) conflicts with "state must reflect actual backend state" principle | Product trust |
| TD-11 | P3 | Template leftovers (`web/README.md`, unused assets, unmounted `KnowledgeGalaxy`) | Hygiene |

## 10. What Hermes Built Well (preserve)

- The **holographic UI identity** — distinctive, performant-conscious (pixel-ratio cap, mobile particle budget, reduced-motion), state-driven coloring. This is the product's face; do not replace with generic SaaS UI.
- The **working, interruptible French voice loop** with correct client/server credential split. It is the only currently proven user value; keep it as the production path during any migration (per ElevenLabs policy in `CLAUDE.md` §12).
- **Clean typed backend contracts** (`AgentStep`/`AgentReply`, `Brain` protocol, `ToolShelf`, deterministic risk policy) — small but exactly the right seams to grow the Skills/gateway architecture onto.
- **Honest system prompt discipline** (DeepSeek prompt forbids fake completion claims) and secure-by-default settings.
- Reproducible deployment.

## 11. Reusable Components

`Brain` protocol (model-provider abstraction seam), `ToolShelf` (skill registry seed), `decide()` policy (autonomy-level seed), `DeviceRepository` (auth seed for a future user/tenant model), `RealtimeGateway` (voice-provider adapter seed), the entire UI shell and state machine (`VoiceState` maps directly to the spec's assistant-state contract).
