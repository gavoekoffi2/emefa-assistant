# EMEFA — Backlog

> New non-blocking ideas land here instead of derailing the current phase (`CLAUDE_EXECUTION_PROMPT.md` §64).

## NOW (Phase 3 — Realtime Voice/Text Core, continued)

- ADR: route voice reasoning through EMEFA backend (ElevenLabs custom-LLM/webhook vs LiveKit) after baseline benchmark — needs owner input on ElevenLabs agent config access
- Approval UI + pending-action persistence for `confirmation_required` runs (prerequisite for the first COMMUNICATE-risk skill)
- Persist backend conversation history (replace in-process dict), shared key with future voice convergence

Done in Phase 3 slice 1 (2026-07-20): DeepSeek function calling, first governed skills (get_profiles, update_business_profile), typed input through `/v1/agent/runs` when voice is offline, conversational onboarding via the agent.

Done in Phase 1 (2026-07-20): `.env.example`, README quickstart, S1 rate limiting, S2 token expiry, structured logging + audit, migration discipline, ADR-001, CI.
Done in Phase 2 (2026-07-20): identity migration + seeds, ProfileRepository + endpoints, prompt context injection, profile panel UI + first-run onboarding.

## NEXT (Phase 3, continued)
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
