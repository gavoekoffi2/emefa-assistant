# EMEFA — Implementation Status

> Read this first when resuming work (per `CLAUDE.md` mandatory reading order).

## Current Phase

**Phase 0 — Audit & Baseline: COMPLETE (2026-07-20).** Entering **Phase 1 — Foundation Stabilization**.

## Goal

Make the existing codebase safe to extend without breaking the working voice product or the holographic UI.

## Completed

- Full repository audit from direct inspection: `docs/audit/REPOSITORY_AUDIT.md`, `docs/audit/CURRENT_ARCHITECTURE.md`, `docs/audit/GAP_ANALYSIS.md`; `docs/CURRENT_STATE_ASSESSMENT.md` filled from template.
- Baseline checks run and recorded: backend `pytest` 27/27 pass; web `oxlint` clean; web tests 4/4 pass; `tsc + vite build` pass (1.2 MB bundle warning, three.js).
- Key architectural finding documented: voice runs entirely on an ElevenLabs dashboard-configured agent; the governed backend `AgentEngine` (+ risk policy, empty `ToolShelf`) is not called by the frontend — "two disconnected brains".
- Security findings classified (S1 rate limiting HIGH; S2 token expiry MEDIUM; S3 ungoverned voice persona MEDIUM; S4 no audit/logging LOW).

## Completed — Phase 1 slice 1 (2026-07-20)

- **S1 fixed:** failure-based rate limiting on `POST /v1/web/session` and `/v1/devices/enroll` (`domain/ratelimit.py`; per-source + global buckets; 429 lockout; only failures count). Configurable via `EMEFA_ACTIVATION_MAX_FAILURES` / `EMEFA_ACTIVATION_WINDOW_SECONDS`.
- **S2 fixed:** device tokens now expire server-side after `EMEFA_SESSION_MAX_AGE_SECONDS` (uses stored `created_at`; expired rows purged lazily on authentication).
- **Observability baseline:** JSON structured logging (`observability.py`), `X-Request-ID` on every response, request logs (method/path/status/duration) for `/v1/*` and `/health`, audit events (`emefa.audit` logger) for enrollment, activation, rejection, rate-limit hits, revocation, agent runs, realtime session issuance. No secrets or message content logged.
- **Migration discipline:** numbered `MIGRATIONS` list + `schema_migrations` table in `DeviceRepository` (existing DBs adopt version 1 transparently via `CREATE TABLE IF NOT EXISTS`).
- **ADR-001** (`docs/adr/ADR-001-identity-model.md`): tenant→user→assistant hierarchy defined; single-tenant instance mode for MVP; devices stay the auth transport. Satisfies the "tenant/auth foundation defined" exit criterion.
- **Handoff hygiene:** `.env.example` completed (all read settings, none invented); README §24 verified quickstart; dead OpenAI-realtime settings removed from `config.py`.
- **CI:** `.github/workflows/ci.yml` running backend pytest and web lint/test/build on push/PR.
- Tests: backend suite now **35 passing** (8 new hardening tests, incl. lockout, expiry+purge, migration tracking, request-ID).

## In Progress

Nothing mid-flight; next slice not started.

## Blocked

- Nothing blocking development. Live provider verification (ElevenLabs/DeepSeek calls) requires secrets not present in this environment — behavior verified through code + existing mock-transport tests only.
- ElevenLabs agent persona/config is dashboard state, not in git; needs export/versioning (owner action or API task).

## Tests

`cd backend && pip install -e ".[test]" && python -m pytest` → 27 pass.
`cd web && npm ci && npm run lint && npm test && npm run build` → all pass.

## Decisions

- No rewrite of any subsystem; ElevenLabs voice path and 3D UI preserved as-is (evidence in audit docs).
- SQLite retained for single-instance MVP; unused OpenAI-realtime settings to be removed when `config.py` is next touched.
- Audit docs written in English (matching spec pack); ops runbook remains French.

## Next

Phase 1 exit gate (roadmap §17) is now satisfied: app starts, UI untouched and working, build passes, tests pass, no critical secret exposure, tenant/auth foundation defined (ADR-001). Remaining Phase 1-adjacent items moved to backlog NEXT (persist conversation state when identity lands).

**Phase 2 — Assistant Identity & Onboarding** is the next slice:
1. Migration 2: implicit tenant/user/assistant rows + `assistant_profile` / `business_profile` tables (per ADR-001).
2. Backend endpoints to read/update the assistant + business profile (device-authenticated).
3. Conversational onboarding flow reusing the existing conversation UI; persisted summary the user can correct.
4. Wire profile context into `DeepSeekBrain` system prompt composition.
Exit gate: create/configure assistant, minimum onboarding persisted, reload without losing setup (roadmap §22).
