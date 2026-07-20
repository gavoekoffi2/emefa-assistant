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

## In Progress

Phase 1 slice 1 (see Next).

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

## Next (Phase 1 — smallest coherent slice, in order)

1. `.env.example` + root README quickstart accuracy.
2. Rate limiting/lockout on `POST /v1/web/session` and `/v1/devices/enroll` (S1).
3. Server-side session expiry via `devices.created_at` (S2).
4. Structured logging + request IDs + minimal audit events (auth, agent runs).
5. ADR-001 minimal identity model (tenant/user/assistant, single-tenant instance).
6. GitHub Actions CI running the four existing check commands.

Phase 1 exit gate (roadmap §17): app starts, UI works, build passes, tests pass, no critical secret exposure, tenant/auth foundation defined.
