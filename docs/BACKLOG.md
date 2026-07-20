# EMEFA — Backlog

> New non-blocking ideas land here instead of derailing the current phase (`CLAUDE_EXECUTION_PROMPT.md` §64).

## NOW (Phase 2 — Assistant Identity & Onboarding)

- Migration 2: implicit tenant/user/assistant rows + assistant/business profile tables (ADR-001)
- Profile read/update endpoints (device-authenticated)
- Conversational onboarding persisting a correctable summary
- Profile context injected into `DeepSeekBrain` prompt composition

Done in Phase 1 (2026-07-20): `.env.example` completed, README quickstart, S1 rate limiting, S2 token expiry, structured logging + request IDs + audit events, migration discipline, ADR-001, CI pipeline.

## NEXT (Phase 3)
- Persist conversation history (replace in-process dict) keyed to identity model
- Wire `/v1/agent/runs` into the product; confirmation UI for `confirmation_required` replies
- Structured tool-calling in `DeepSeekBrain` (stop discarding tool descriptions)
- Version the ElevenLabs agent persona/config in-repo; evaluate custom-LLM/webhook mode so voice reasoning runs through the EMEFA runtime (ADR)
- Voice baseline benchmark (latency, interruption, cost per active minute) before any migration work

## LATER

- Memory system (structured first; provenance, user inspection/correction/forget)
- Skills gateway grown from `ToolShelf` (schemas, permissions, audit, timeouts); first native skills (memory.retrieve, task.create)
- Administrative slices: daily brief, meeting preparation, document generation (OfficeCLI spike: `docs/spikes/OFFICECLI_EVALUATION.md`)
- Business development slice: ICP → discovery → qualification → outreach drafts (approval-gated)
- Durable workflows (weekly prospecting, morning brief), approval inbox, kill switch
- Code-split three.js / lazy-load `HolographicUniverse`; real telemetry data in HUD (replace decorative values)
- Component/E2E tests for web (replace regex source tests); tenant-isolation and prompt-injection test suites
- Remove dead config (`EMEFA_OPENAI_API_KEY`, `EMEFA_REALTIME_MODEL`, `EMEFA_REALTIME_VOICE`) and template leftovers; decide fate of unmounted `KnowledgeGalaxy`

## RESEARCH

- LiveKit as realtime transport vs ElevenLabs custom-LLM mode (benchmark-gated; LiveKit ≠ STT/TTS)
- Economical STT/TTS providers for French + African accents; ElevenLabs stays premium/fallback
- African language evaluation plans (Ewe, Kabiye, Mina) — end-to-end, evidence-based
- MCP adapter/registry design (only when an MVP integration needs it)
- Agent Zero gateway (bounded research delegate; optional for MVP)
- Multi-worker/multi-instance story (SQLite limits, session store) for platformization
