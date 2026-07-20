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

## Completed — Phase 2 slice 1: identity & profile foundation (2026-07-20)

- **Migration 2** (`domain/storage.py`, shared migration runner extracted from `DeviceRepository`): `tenants` / `users` / `assistants` / `business_profiles` tables with ADR-001 single-tenant seed rows (`ten_default` / `usr_default` / `ast_default`); `devices.user_id` column added. Existing databases upgrade transparently.
- **`ProfileRepository`** (`domain/profiles.py`): assistant profile (name, primary language, interaction style) and business profile (owner, role, company, industry, offer, target customers, goals, constraints); partial updates; `system_context()` composes the French profile block for the model prompt.
- **API** (`api/profile.py`): device-authenticated `GET/PATCH /v1/assistant/profile` and `/v1/assistant/business`, length-bounded fields, audit events (field names only, never values).
- **Prompt composition:** `DeepSeekBrain` accepts a `context_provider`; `create_app` wires `profiles.system_context` so agent replies use assistant identity + business context. Base system prompt de-hard-coded from a single named user.
- Tests: **41 passing** (6 new: seeding, partial persistence, context composition, auth requirement, API roundtrip, prompt injection of context via mock transport).

## Completed — Phase 2 slice 2: profile UI & first-run onboarding (2026-07-20)

- **`web/src/ProfilePanel.tsx`**: HUD-styled dialog to view/edit the assistant identity (name, interaction style) and the full business profile; loads via `GET /v1/assistant/*`, saves via `PATCH`; French copy; mobile full-screen; accessible (dialog role, labels, alerts).
- **First-run onboarding (progressive):** on entering the voice room, if the business profile is empty the panel opens automatically with a "Faisons connaissance" invitation; user can defer ("Plus tard").
- Header nav: decorative "Mémoire/Outils" buttons replaced by a functional "Profil" toggle (honest-state principle).
- Checks: web lint clean, 5/5 web tests, build OK; backend 41/41.

## Phase 2 exit gate status (roadmap §22)

Met: see/edit profile ✓, persist business context ✓, reload without losing setup ✓ (server-side persistence). Remaining before closing Phase 2: *conversational* onboarding through the agent itself — deliberately deferred to Phase 3 (voice/text convergence), since today's conversation brain is the ElevenLabs dashboard agent which cannot call our profile APIs. Documented in BACKLOG NEXT.

## In Progress

Nothing mid-flight.

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
