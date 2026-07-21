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

## Completed — Phase 3 slice 1: text through the EMEFA runtime + first governed skills (2026-07-20)

- **Structured tool-calling in `DeepSeekBrain`** (OpenAI-compatible function calling): tool schemas sent when available, `tool_calls` responses parsed into `RequestedAction` (with `call_id`), prior tool executions replayed to the provider as compliant assistant/tool message pairs. `RequestedAction.call_id` and `AgentTool.parameters` added; engine records call id + arguments in history.
- **First governed skills** (`emefa/skills.py`): `get_profiles` (PERSONAL_READ → RUN) and `update_business_profile` (LOCAL_WRITE → RUN, JSON-schema parameters, field allowlist, audit event). Registered in the app's `ToolShelf`, so every execution passes the deterministic risk policy. This enables **conversational onboarding**: "Mon entreprise s'appelle Horizon…" persists to the business profile and is visible/correctable in the Profil panel.
- **Typed input now reaches the backend**: when no voice session is live, the command dock posts to `/v1/agent/runs` (thinking state, per-device conversation continuity, profile-aware replies). All four run statuses surfaced honestly in French, including a truthful "approval flow coming" message for `confirmation_required`. Live-session behavior unchanged (`sendUserMessage`).
- Tests: backend **45 passing** (4 new: skill handlers, schema exposure, DeepSeek tool-call emission/replay via mock transport, end-to-end run that persists the profile through the gateway); web **6 passing**, lint/build clean.

## Known honest limitation

Voice (ElevenLabs session) and the backend text path still have **separate conversation contexts and separate brains**; they share only the persisted profile. Full convergence requires the voice-routing ADR (custom-LLM/webhook vs LiveKit) and a measured baseline — next major step.

## Completed — Phase 3 slice 2: durable conversation history (2026-07-20)

- **Migration 3:** `conversation_turns` table (tenant/user-scoped per ADR-001 discipline, indexed by conversation).
- **`ConversationStore`** (`domain/conversations.py`): append-only JSON payloads, `recent(limit=12)` window, `forget()`.
- **`AgentEngine`** now takes a `ConversationMemory` (protocol) — the app injects the SQLite store; an in-process fallback remains for tests. Text conversations survive server restarts and are correct under future multi-worker setups (TD-6 resolved for the text path).
- Tests: **48 passing** (3 new: store roundtrip/trim/forget, engine restart continuity, API-level continuity across `create_app` instances).

## Completed — mobile bundle slimming (2026-07-20)

- `HolographicUniverse` (three.js) is now a lazily loaded chunk: initial JS 1,203 kB → 669 kB (gzip 319 kB → 185 kB); hologram chunk 540 kB loads asynchronously after the shell (TD-9 first step). No behavior change; reduced-motion and mobile budgets unchanged.

## Completed — approval loop end-to-end (2026-07-20)

- **Migration 4:** `pending_actions` table (tenant/user-scoped, indexed by conversation/status).
- **`ApprovalRepository`** (`domain/approvals.py`): create/get/list-pending/resolve with JSON arguments; replay of a resolved action returns 404.
- **`AgentEngine`** refactor: shared `_advance` loop; on an ASK decision the context is persisted so the action can resume after reload/restart; new `execute_approved()` runs the approved tool then lets the brain conclude (chained approvals supported).
- **API:** `GET /v1/agent/approvals`, `POST /v1/agent/approvals/{id}/decision` (approve/reject, device-scoped, 404 on foreign/resolved actions); `RunResponse` gains `action_id` and a `rejected` status. Audit events: approval_created/approved/rejected.
- **First real destructive skill:** `reset_business_profile` (DESTRUCTIVE → ASK; optional field list; irreversible-marked description; audit) — approval binds to the exact persisted action, satisfying "approval must bind to exact action" (`CLAUDE_EXECUTION_PROMPT` §37).
- **Web:** approval card (alertdialog) with Approuver/Refuser, argument preview, French skill labels; pending approvals restored on page load; honest `rejected` surface. Amber styling distinct from the cyan HUD.
- Tests: backend **52 passing** (approve executes + profile actually cleared; reject never executes; replay/foreign 404; unknown-tool guard); web **7 passing**; lint/build clean.

## Completed — tasks & commitments foundation (2026-07-20)

- **Migration 5:** `tasks` table (tenant/user-scoped; status open/done; optional ISO due date).
- **`TaskRepository`** (`domain/tasks.py`): create (due-date validated), open list ordered by due date, complete (idempotence guarded); bucket classification `en_retard / aujourdhui / a_venir / sans_echeance`.
- **Three governed skills** registered in the shelf: `create_task`, `list_tasks`, `complete_task` (LOCAL_WRITE/PERSONAL_READ → RUN policy; structured error returns; audit events). "Rappelle-moi de relancer Horizon demain" now persists a real commitment through the gateway.
- **`GET /v1/tasks`** (device-authenticated) exposes open tasks with buckets for the future tasks/brief UI.
- Tests: backend **55 passing** (repository incl. buckets/ordering/idempotence, skill flow incl. error paths, conversation→API end-to-end).

## Completed — daily brief + tasks HUD panel (2026-07-20)

- **`get_daily_brief` skill** (PERSONAL_READ): deterministic brief composition — open tasks grouped by bucket, count, business goals and company name. The flagship demo question "Qu'est-ce qui mérite mon attention aujourd'hui ?" now has grounded data behind it.
- **`POST /v1/tasks/{id}/complete`** (device-authenticated, audited, 404 once closed).
- **Tasks panel** in the HUD ("Tâches" nav): open commitments grouped En retard / Aujourd'hui / À venir / Sans échéance, per-task Terminer button, empty-state guidance, and a "Brief du jour" quick action that sends the flagship question through the active channel (voice session if live, EMEFA runtime otherwise). `sendMessage` extracted so typed input, quick actions, and future buttons share one path.
- Tests: backend **57 passing** (brief composition, completion endpoint idempotence), web **8 passing**; lint/build clean.

## Completed — honest HUD telemetry, TD-10 (2026-07-20)

- **`GET /v1/system/status`** (device-authenticated): brain configured?, voice configured?, registered skills with risk levels, open task count, schema version. No decorative values.
- **HUD wired to reality:** "16 sources synchronisées" → real skill count; "NOYAU COGNITIF 98.7%" → EN LIGNE / NON CONFIGURÉ from actual brain state; "LIAISON VOCALE" states ACTIVE / VEILLE / NON CONFIGURÉE; radar "16 NŒUDS" → real open-commitment count; "CHIFFREMENT ACTIF" only claimed on HTTPS (CONNEXION LOCALE otherwise). Status refreshes after each agent run and when the Tasks panel closes. Purely decorative ambiance (hex flux, radar sweep) kept — it decorates without asserting facts.
- Tests: backend **59 passing** (status content incl. skill risks; unconfigured brain reported honestly), web **9 passing** (asserts fake numbers are gone); lint/build clean.

## Completed — conversational assistant identity (2026-07-20)

- **`update_assistant_profile` skill** (LOCAL_WRITE → RUN): durable adjustments to the assistant's name, primary language, or interaction style through conversation ("tutoie-moi", "sois plus concise"). Field allowlist, blank-value rejection, audit event. Changes flow into `system_context()` so the next turns immediately reflect the new style. Backend **60 passing**.

## Completed — OpenRouter brain option (2026-07-20)

- New settings `EMEFA_OPENROUTER_API_KEY`, `EMEFA_OPENROUTER_MODEL` (default `deepseek/deepseek-chat`), `EMEFA_OPENROUTER_BASE_URL`. The existing OpenAI-compatible adapter is reused with a different base URL — no new code path to maintain. Selection order: explicit brain (tests) → DeepSeek key → OpenRouter key → not configured.
- The owner supplied an OpenRouter key (kept out of the repository; must be set as `EMEFA_OPENROUTER_API_KEY` in the server `.env` — see `docs/DEPLOIEMENT.md`). **Live verification was not possible from this development sandbox** (its network policy denies `openrouter.ai`); first production start should confirm via `/v1/system/status` (`brain_configured: true`) and a text exchange. If the default model name is rejected, set `EMEFA_OPENROUTER_MODEL` to a current tool-capable model from openrouter.ai/models.
- Backend **61 passing** (new test: OpenRouter key ⇒ brain configured).

## Completed — voice→brain bridge, Custom LLM endpoint (2026-07-20)

- **`POST /v1/voice-llm/chat/completions`**: OpenAI-compatible endpoint for the ElevenLabs "Custom LLM" option. Injects EMEFA's profile context (assistant + business) as a leading system message, preserves the agent persona message, forces the configured provider/model, and forwards streaming (SSE passthrough) or non-streaming requests to the same provider as the text brain.
- **Auth:** `EMEFA_VOICE_LLM_TOKEN` bearer secret (constant-time compare); 503 when the token or the provider is unconfigured; upstream failures map to 502; audit events without content logging.
- **Shared provider resolution** in `create_app`: DeepSeek direct → OpenRouter → not configured, used by both the text brain and the voice bridge.
- Deployment guide: dashboard steps + instant rollback (re-select the ElevenLabs LLM).
- Tests: backend **66 passing** (auth/token, 503 unconfigured, context injection order, SSE passthrough, upstream error mapping).
- **Remaining for the Phase 3 exit gate:** owner flips the ElevenLabs agent to the Custom LLM URL, then live validation of latency/interruption. Voice conversation memory (feeding `ConversationStore` from voice turns) is the next convergence step after the bridge is confirmed working.

## Completed — Phase 4 memory MVP (2026-07-20)

- **Migration 6:** `memories` table (tenant/user-scoped, category, provenance `source`, timestamps). Structured entries — not raw chat storage.
- **`MemoryRepository`:** remember (whitespace-normalised, 500-char cap, category validated), list, hard forget, and a **bounded** `context_block()` (max 12 entries × 200 chars) so memory can never crowd out conversation.
- **Three governed skills:** `remember` (LOCAL_WRITE; prompts a short self-contained sentence, warns against unsolicited sensitive data), `list_memories` (PERSONAL_READ), `forget_memory` (**DESTRUCTIVE → approval loop**). "Retiens que le fournisseur livre le mardi" now persists a controllable memory.
- **Shared context composition:** `compose_context()` (profiles + memory block) now feeds **both** the text brain and the voice Custom-LLM bridge — voice and text share profile *and* memory.
- **User control (spec §26):** `GET /v1/memories`, `DELETE /v1/memories/{id}` (404 once gone, audited) and a **Mémoire panel** in the HUD (category chips, dates, per-entry "Oublier", honest empty state).
- Tests: backend **71 passing** (repository bounds, skills incl. risk levels, API auth/delete, context composition, voice-bridge memory injection); web **10 passing**; lint/build clean.

Phase 4 exit gate status: memory survives sessions ✅, explicit preference ✅, correction ✅ (delete + re-remember; panel), forget ✅ (user-direct + approval-gated via agent), bounded injection ✅, cross-tenant leakage N/A single-tenant (scoped columns ready). Remaining for full Phase 4: episodic summaries and memory export.

## Completed — user control & injection framing (2026-07-20)

- **`GET /v1/memories/export`**: JSON attachment (`emefa-memoire.json`) with provenance and timestamps — Phase 4 export requirement met (inspect/correct/export/delete now all exist).
- **`DELETE /v1/agent/conversation`**: user-initiated wipe of the text-brain conversation history (audited, 204); the next exchange starts fresh.
- **Prompt-injection framing**: `compose_context()` now opens with an explicit guard stating profile/memory content is user data and never instructions — applied to both text brain and voice bridge.
- **Mémoire panel**: "Exporter la mémoire" and "Effacer la conversation" buttons with honest status feedback.
- Tests: backend **74 passing** (export attachment, conversation clear verified through the brain's next-turn history, framing assertion); web **10 passing**; lint/build clean.

## Verified — real-server end-to-end run (2026-07-20)

Beyond the 74 backend / 10 web automated tests, the actual product was booted (uvicorn + built frontend) and the full user journey exercised over HTTP:

- **Without any provider key:** wrong activation code → 403; activation → session cookie; `/v1/system/status` reports `brain_configured: false` honestly with 11 skills; typed request answers "Le moteur de langage EMEFA n'est pas encore configuré."; tasks/memories empty; memory export downloads as attachment; conversation wipe → 204; voice bridge → 503; the lazy hologram chunk is served.
- **With the production configuration path** (env vars pointing the OpenRouter settings at a local OpenAI-compatible mock, since the dev sandbox blocks `openrouter.ai`): `brain_configured: true`; "Retiens que le fournisseur livre le mardi" → tool call → `remember` skill → memory persisted (visible via `/v1/memories`) → answer in 2 turns; the voice bridge streams SSE with the correct bearer token and rejects a wrong token with 401.

The only step never exercised against the real OpenRouter service is the network call itself — to be confirmed at first production start (see Blocked list).

## Completed — voice↔text conversation convergence (2026-07-20)

- **Voice exchanges are now persisted** by the Custom-LLM bridge into the shared `ConversationStore` under `voice:default` (single-user channel; the bridge has no device binding — revisit at multi-tenant time). Non-streaming answers are captured directly; streamed answers are **reassembled from SSE deltas** in a passthrough relay that never delays the audio path.
- **Cross-channel context:** the text brain's context now appends a bounded recap (last 6 turns, 200 chars each) of recent voice exchanges — a conversation started by voice can continue in writing. The recap is deliberately absent from the voice bridge's own context (the provider already receives the full voice history in each request), avoiding duplication.
- **"Effacer la conversation" wipes both channels** (device text history + voice channel).
- The app now uses a single shared `ConversationStore` instance (engine + bridge + context composition).
- Tests: backend **77 passing** (persistence + text-context recap + no-duplication guarantee, SSE reassembly incl. UTF-8 split, both-channel wipe); web unchanged (10 passing).

With this, the Phase 3 "text and voice share context" exit criterion is implemented in both directions (voice gets profile+memory; text gets voice recap). Live validation still requires the owner's ElevenLabs dashboard switch.

## Completed — first external capability: governed SMTP e-mail (2026-07-20)

- **`SmtpEmailSender`** (`infrastructure/email.py`): stdlib `smtplib` via `asyncio.to_thread` (no new dependency), STARTTLS + login, provider-neutral (Gmail app password, Outlook, any host). Settings `EMEFA_SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/STARTTLS`; credentials server-side only.
- **`send_email` skill** (COMMUNICATE → **ASK**): every send goes through the approval card; recipient validated, subject/body capped, single recipient per send; server refusals surfaced as errors, not fake success; audit logs recipient **domain only**.
- **Honest capability listing:** the skill is registered only when SMTP is configured, so `/v1/system/status` and the HUD never advertise an e-mail ability that doesn't exist.
- This satisfies the **Phase 5 exit-gate pattern**: a real external capability through Skill Registry → permission check → adapter → verification (SMTP acceptance) → audit, with no bypass. It is also the first slice of the **Phase 6 e-mail MVP** (send path; inbox/reply flows still open).
- Tests: backend **82 passing** (adapter STARTTLS/login/message assembly via faked `smtplib.SMTP`, conditional registration + policy = ASK, input validation, approval E2E proving *nothing is sent before approval* and *rejection never sends*).

## Completed — Phase 7 seed: local sales pipeline (2026-07-20)

- **Migration 7:** `prospects` table (tenant/user-scoped; stages `nouveau → contacté → qualifié → proposition → gagné/perdu`; dated next action).
- **`ProspectRepository`:** add/update with field allowlist and ISO-date validation, open-pipeline listing ordered by follow-up date, `due_follow_ups()` (open stages only).
- **Three governed skills:** `add_prospect`, `list_pipeline` (PERSONAL_READ), `update_prospect` (stage enum enforced). "Ajoute Ama Mensah de Mensah Logistics, relance jeudi" persists a tracked prospect.
- **Brief integration:** `get_daily_brief` now includes `due_follow_ups` — the flagship question surfaces overdue sales follow-ups, which pair naturally with the approval-gated `send_email` for relances.
- **`GET /v1/prospects`** for the future pipeline UI.
- Deliberately excluded (needs vetted providers + anti-spam guardrails): prospect discovery, enrichment, automated outreach. Tracking only — no uncontrolled prospecting (CLAUDE.md §29).
- Tests: backend **86 passing** (repository incl. won-prospect exits pipeline, skills incl. stage validation, brief integration, conversation→API end-to-end).

## Completed — reconciled e-mail suite + voice actions (2026-07-20)

**Audit first:** the requested `email_search/read/create_draft/send` skills and the "graphistegpt" account did **not** exist anywhere in the repo (all branches searched); `main` had simply been fast-forwarded to commit 84e552a. Rather than a second integration, the existing SMTP skill was **reconciled**: `send_email` → **`email_send`** (same COMMUNICATE→approval path), plus a new stdlib-`imaplib` client providing **`email_search`**, **`email_read`** (both PERSONAL_READ, results framed as external data — never instructions), and **`email_create_draft`** (LOCAL_WRITE, saved to the mailbox Drafts folder, no send). Settings `EMEFA_IMAP_*` with fallback to the SMTP credentials (single graphistegpt account). Skills register only when configured.

**Voice bridge now routes through the governed engine:** each Custom-LLM turn runs `AgentEngine.run()` on the shared voice conversation — voice has the same skills, policy, approvals, and history as text. `confirmation_required` becomes a **pending approval + oral announcement** ("l'envoi attend votre approbation, la carte vient d'apparaître"); the reply is served as synthesized OpenAI SSE. Voice-channel approvals are listed/decidable from any authenticated device (single-user mode, documented), and the HUD polls approvals every 4 s during a live session so the card surfaces mid-conversation. The now-redundant streaming proxy (`infrastructure/voice_llm.py`) was removed.

**Pipeline panel (Phase 7)** in the HUD: prospects grouped by stage, due follow-ups highlighted with a RELANCE badge and a call-to-action pairing with `email_send`.

**Verified end-to-end on the real server** (uvicorn + built frontend + local OpenAI-compatible mock + a **real local SMTP server** on loopback): spoken request → SSE announcement with recipient/subject → pending approval visible in `/v1/agent/approvals` → approval → **message actually delivered over SMTP** (`From: graphistegpt@gmail.com`, `To: ama@exemple.com`, `Subject: Test EMEFA` observed on the wire) → next voice turn answers "l'e-mail est parti". **Honest limit:** the audio/microphone leg (ElevenLabs ↔ browser) cannot run from this sandbox — validate at the deployment after switching the agent to the Custom LLM URL.

Tests: backend **85 passing**, web **12 passing**, lint/build clean.

## Completed — Phase 8 seed: proactive morning brief (2026-07-20)

- **Migration 8:** `briefings` table (one per date, upsert, `emailed` flag).
- **`compose_daily_brief` / `format_brief_text`** extracted from the skill so the scheduler and the API share the same deterministic composition (tasks by bucket, due sales follow-ups, goals) and French plain-text rendering.
- **Bounded scheduler** (`emefa/scheduler.py`): sleeps until `EMEFA_BRIEF_HOUR` (off by default — no proactive work without explicit configuration), runs one idempotent job per day (per-iteration error handling, ≥60 s guard, clean cancellation in the app lifespan). Per §34: explicit stop conditions, no unbounded autonomy.
- **Standing scoped approval (§24 level 5):** `EMEFA_BRIEF_EMAIL_TO` authorizes exactly one e-mail per day (the brief) — sent at most once (flag-guarded), revocable by removing the variable. Without it, the brief is stored but never sent.
- **`GET /v1/briefings/today`** + HUD **"Votre brief du jour est prêt"** dismissible strip that displays the brief in the answer panel.
- Tests: backend **90 passing** (schedule math, repository upsert/emailed, French rendering, job idempotence incl. *e-mailed exactly once* and *never without the standing approval*, endpoint auth/404/content); web **13 passing**; lint/build clean.

## Completed — hardening & doc reconciliation (Phase 10 start, 2026-07-20)

- **IMAP query injection fixed:** the `email_search` query (produced by the model — untrusted output) is now sanitised — quotes and all control characters, CR/LF included, are neutralised before building the `SEARCH TEXT "…"` command, so it cannot inject IMAP protocol commands. Regression test added.
- **`CURRENT_STATE_ASSESSMENT.md` reconciled:** a prominent banner marks it as the point-in-time Phase 0 baseline and points to `IMPLEMENTATION_STATUS.md` as the living record, listing the major facts that changed since the audit (unified governed brain, 14 skills, memory/approvals/audit, migration 8). The audit body is preserved as a historical record rather than rewritten.
- Tests: backend **91 passing**; web **13 passing**; lint/build clean.

## Completed — voice channel least-privilege (Phase 10, 2026-07-20)

Acting on the security review's one defense-in-depth item: the voice channel now runs a **reduced tool shelf** (`build_tool_shelf(..., include_mailbox_read=False)`) via a dedicated `voice_agent` engine. `email_search`/`email_read` are withheld from the voice path, so the ElevenLabs-shared bearer secret can no longer cause live inbox contents to be returned in-band. Approval-gated `email_send` stays available on voice (the request creates a pending approval; the full-shelf engine executes it after HUD approval). Test proves the voice shelf omits the two mailbox-read tools while keeping `email_send`; the text shelf keeps all. Backend **92 passing**.

## Completed — Phase 9: integrated demo experience (2026-07-20)

Turns the Phases 0–8 capabilities into one coherent, honest, demonstrable flow — no new large feature, no rewrite of stable components.

- **Truthful visual states:** added `awaiting` (amber, "EN ATTENTE DE VOTRE APPROBATION") and `success` (green, "TERMINÉ") to the state machine, wired to the *real* backend reply — `confirmation_required` → awaiting, `completed` → success (relaxes to listening/idle), `blocked`/`failed` → error. The holographic HUD colour reflects each. Now covers listening / understanding-working (thinking) / awaiting approval / success / error.
- **Guided scenarios launcher** (`GET /v1/demo/scenarios` + HUD tray): the 5 requested prompts, each sent through the **real** governed engine (voice session if live, `/v1/agent/runs` otherwise), with an honest availability badge derived from actual system state: **RÉEL** (executive brief), **ASSISTÉ** (meeting prep, encadred autonomy), **APERÇU** (document creation, prospect discovery — capabilities that do not exist yet).
- **Anti-fake-completion guard (§25):** `compose_context()` now instructs the brain to never claim an action its tools did not execute, to be explicit that prospect discovery and document generation are unavailable, and to not expose internal reasoning. Applies to text and voice.
- **Result surfaces reused, not rebuilt:** brief → answer panel + strip; tasks/pipeline/memory → existing panels; consequential actions → existing approval card. Continuity voice↔text preserved (shared conversation + context).
- **Verified end-to-end on the real server** (uvicorn + built frontend + local OpenAI-compatible mock): scenario 1 drives `get_daily_brief` for real (2 turns, real brief); scenarios 3 & 4 return honest "not available yet" answers with **zero fabricated prospects in the DB** — no simulation presented as real execution. Conversation continuity confirmed (history persists across turns; cleared cleanly between isolated checks).
- Tests: backend **95 passing** (scenario catalog honesty, anti-fake guard in context, executive-brief end-to-end); web **15 passing** (scenario tray + badges, awaiting/success states); lint/build clean.

### Phase 9 — honest scenario status
| Scénario | Statut | Réalité |
|---|---|---|
| 1. Briefing exécutif | **RÉEL** | `get_daily_brief` compose tâches + relances + objectifs |
| 2. Préparation de réunion | ASSISTÉ | assemble profil/pipeline/tâches (pas d'agenda dédié) |
| 3. Création de document | APERÇU | non implémenté — proposé en texte/brouillon, jamais simulé |
| 4. Découverte de 10 prospects | APERÇU | non implémenté (anti-spam) — suivi manuel réel du pipeline |
| 5. Autonomie hebdo + approbation | ASSISTÉ | brief récurrent réel + envoi toujours sous approbation |

## In Progress

Nothing mid-flight.

## Blocked on product owner

1. **ElevenLabs agent governance (S3):** need the dashboard agent's persona/config exported into the repo, or API access to fetch it.
2. **Voice routing ADR + baseline benchmark:** requires live credentials to measure latency/interruption/cost before choosing ElevenLabs custom-LLM vs LiveKit.
3. **First external integrations (email/calendar/documents):** provider choices and credentials needed before Phase 5/6 slices can be real (no fake integrations).

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
