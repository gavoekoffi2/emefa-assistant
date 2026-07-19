# EMEFA — IMPLEMENTATION_ROADMAP.md

> **Document type:** Brownfield implementation roadmap, engineering execution phases, quality gates, and MVP delivery plan  
> **Project:** EMEFA  
> **Primary implementer:** Claude / coding agent  
> **Existing implementation:** Hermes-created EMEFA codebase  
> **Purpose:** Convert the architecture specifications into an executable engineering sequence that preserves valuable existing work, removes unsafe shortcuts incrementally, and delivers a demonstrable production-grade MVP without uncontrolled scope expansion.  
> **Critical rule:** DO NOT restart EMEFA from zero. Audit the existing repository first, preserve what works, and evolve the codebase through tested incremental changes.

---

# 1. Mission

The goal is not to build every future EMEFA capability now.

The goal is to deliver a coherent MVP proving this promise:

> A business owner can create a personalized EMEFA that understands the business, communicates naturally by voice/text, remembers relevant context, performs useful administrative work, continuously assists with business development, and executes governed workflows through real tools.

The implementation must prioritize:

```text
Real Value
Reliability
Security
Extensibility
Demonstrability
Cost Discipline
```

over:

```text
Feature Count
Architectural Fashion
Visual Gimmicks
Premature Marketplace Complexity
```

---

# 2. Non-Negotiable Brownfield Rule

Hermes has already created significant work, including a distinctive interface.

Claude must begin with:

```text
READ
→ RUN
→ TEST
→ MAP
→ DECIDE
→ MODIFY
```

Never:

```text
DELETE
→ REBUILD FROM SCRATCH
```

unless a component is demonstrably unsalvageable and the replacement is documented.

---

# 3. Preserve Product Identity

The existing EMEFA experience reportedly includes a futuristic/JARVIS-inspired 3D interface.

Preserve valuable:

- 3D visual identity;
- interaction concepts;
- animations;
- working UI components;
- existing routes;
- working backend functionality;
- reusable infrastructure.

Improve rather than erase.

The visual experience should support utility.

Do not turn EMEFA into a generic SaaS dashboard.

---

# 4. Repository Audit — Mandatory First Phase

Before feature implementation, inspect the entire repository.

Produce:

```text
docs/audit/REPOSITORY_AUDIT.md
```

Include:

```text
Technology stack
Repository structure
Frontend architecture
Backend architecture
Database
Authentication
Voice implementation
AI/model integration
Existing tools/functions
Existing memory
Existing 3D/UI architecture
Environment/configuration
Deployment
Tests
Security risks
Dead code
Technical debt
Working features
Broken features
```

No major refactor before this audit.

---

# 5. Run Existing Product

Claude must attempt to run:

```text
frontend
backend
database
workers if any
tests
lint
typecheck
build
```

Document exact results.

If blocked by missing secrets/services:

- identify blocker;
- use mocks where safe;
- do not invent production credentials.

---

# 6. Baseline Screenshots / Behavior Record

Before major UI changes, preserve baseline evidence:

- key screens;
- voice interaction;
- onboarding;
- assistant view;
- settings;
- existing workflows.

Use screenshots/tests where tooling permits.

Purpose: avoid accidental regression of Hermes's good work.

---

# 7. Architecture Map

Produce:

```text
docs/audit/CURRENT_ARCHITECTURE.md
```

Map:

```text
Browser
Frontend
API
Database
AI provider
Voice provider
External services
Realtime channels
Storage
```

Then compare with target architecture.

---

# 8. Gap Analysis

Produce:

```text
docs/audit/GAP_ANALYSIS.md
```

For each target capability:

```text
Already exists
Partially exists
Missing
Unsafe implementation
Needs migration
```

Do not implement duplicate systems.

---

# 9. Architecture Decision Records

Create only necessary ADRs.

Initial candidates:

```text
ADR-001 Tenant model
ADR-002 Authentication
ADR-003 AI/model abstraction
ADR-004 Voice architecture
ADR-005 Workflow execution
ADR-006 Memory storage/retrieval
ADR-007 Tool/Skill gateway
ADR-008 Document generation provider
```

If existing architecture already makes a sound choice, document and retain it.

---

# 10. Delivery Strategy

Use vertical slices.

Bad:

```text
Build entire memory layer
then entire workflow layer
then entire UI
```

Preferred:

```text
One end-to-end valuable workflow
→ stabilize
→ next workflow
```

Each slice should reach user-visible value.

---

# 11. Phase Structure

Implementation phases:

```text
Phase 0 — Audit & Baseline
Phase 1 — Foundation Stabilization
Phase 2 — Assistant Identity & Onboarding
Phase 3 — Realtime Voice/Text Core
Phase 4 — Memory & Personalization MVP
Phase 5 — Skill/Tool Gateway
Phase 6 — Administrative Assistant MVP
Phase 7 — Business Development MVP
Phase 8 — Durable Workflows & Autonomy
Phase 9 — Integrated Demo Experience
Phase 10 — Hardening & Deployment Handoff
```

Do not skip gates.

---

# 12. Phase 0 — Audit & Baseline

Deliverables:

```text
REPOSITORY_AUDIT.md
CURRENT_ARCHITECTURE.md
GAP_ANALYSIS.md
Risk list
Baseline test/build report
Prioritized migration plan
```

Exit criteria:

- repository understood;
- existing app runnable or blockers documented;
- no unnecessary rewrite planned;
- major security issues identified.

---

# 13. Phase 1 — Foundation Stabilization

Goal:

Make existing codebase safe enough to extend.

Tasks depend on audit, potentially:

```text
Fix broken build/typecheck
Normalize environment config
Remove exposed secrets
Establish server-side auth checks
Establish tenant context
Add structured logging
Add error handling
Add migrations discipline
Add test harness
```

Do not over-refactor.

---

# 14. Phase 1 — Tenant Model

If absent, introduce canonical:

```text
Tenant
User
Membership
Assistant
```

Minimum:

```text
tenant_id
user_id
assistant_id
```

propagated through domain.

Single-user MVP may still use tenant architecture internally.

---

# 15. Phase 1 — Security Baseline

Before tool access:

- no secrets in frontend;
- no unrestricted shell;
- no direct ungoverned provider credentials;
- tenant filtering;
- input validation;
- safe CORS;
- secure session/auth;
- dependency/secret scanning where practical.

Block critical vulnerabilities first.

---

# 16. Phase 1 — Quality Baseline

Commands must exist/documented:

```text
install
dev
test
lint
typecheck
build
```

CI should run relevant checks.

Do not accept “works on my machine” as gate.

---

# 17. Phase 1 Exit Gate

Must pass:

```text
App starts
Core existing UI works
Build passes
Critical tests pass
No known critical secret exposure
Tenant/auth foundation defined
```

---

# 18. Phase 2 — Assistant Identity & Onboarding

Goal:

A user can create/configure their EMEFA.

Implement:

```text
Assistant profile
Name
Primary language
Voice preference
Interaction preference
Business profile
Role
Initial permissions
```

Preserve existing UI where useful.

---

# 19. Conversational Onboarding

Build adaptive onboarding:

```text
Who are you?
What does your business do?
Who are your customers?
What are your priorities?
Which tasks consume time?
Which tools do you use?
What should require approval?
```

Do not require all fields.

---

# 20. Onboarding Summary

At end:

> “Voici ce que j'ai compris.”

Show structured summary.

User can correct.

Persist canonical data.

---

# 21. Initial ICP

For business users, capture enough for prospecting:

```text
Offer
Ideal customer
Geography
Industry
Company size if relevant
Pain solved
```

Can be refined later.

---

# 22. Phase 2 Exit Gate

User can:

- create assistant;
- complete minimum onboarding;
- see/edit profile;
- persist business context;
- reload without losing setup.

---

# 23. Phase 3 — Realtime Voice/Text Core

Goal:

Natural multimodal conversation using same backend logic.

Architecture:

```text
Voice/Text
→ Session Orchestrator
→ Context
→ Model
→ Skills
→ Response
```

No separate voice brain.

---

# 24. Voice Provider Strategy

Do not hard-code ElevenLabs as mandatory.

Use abstraction:

```text
VoiceTransport
STTProvider
TTSProvider
RealtimeModelProvider
```

LiveKit can be considered for realtime transport/orchestration where technically appropriate.

Validate exact current capabilities before implementation.

---

# 25. Cost-Aware Voice

MVP goals:

- low latency;
- interruptibility;
- French quality;
- configurable voices;
- provider flexibility;
- cost visibility.

Do not chase perfect voice cloning.

---

# 26. African/French Voice Requirement

Voice selection UX should support listening before selection.

Prioritize authentic:

- French voices;
- African Francophone accents where providers legitimately offer them;
- multilingual voices.

Do not label a voice “African” based on guesswork.

Store metadata only when verified.

---

# 27. Language Configuration

User can choose:

```text
Primary language
Voice
Optional secondary languages
```

Future local African languages remain extensible.

Do not promise unsupported languages as production-ready.

---

# 28. Voice Interruptions

Support:

```text
User interrupts assistant
→ stop playback/generation
→ process new turn
```

Critical for JARVIS-like feel.

---

# 29. Voice UI

Preserve 3D assistant identity.

Visual states may include:

```text
Idle
Listening
Thinking
Speaking
Working
Waiting for approval
Error
```

State must reflect actual backend state.

---

# 30. Phase 3 Exit Gate

Demonstrate:

```text
Voice session starts
User speaks French
Assistant responds naturally
User interrupts
Text and voice share context
Voice selection persists
```

---

# 31. Phase 4 — Memory & Personalization MVP

Implement canonical memory gateway.

Start with:

```text
User profile
Organization profile
Preferences
Contacts basics
Project context
Commitments
```

Avoid overbuilding knowledge graph.

---

# 32. Memory Storage

Use structured database first.

Add vector retrieval only where needed.

Never make vector store sole source of truth.

---

# 33. Memory APIs

Minimum:

```text
get_context
save_explicit_preference
update
forget
search_relevant
```

All tenant-scoped.

---

# 34. Provenance

Store:

```text
source
trust
timestamps
```

At least for important facts/preferences.

---

# 35. Memory UX

User can:

- inspect core profile/preferences;
- correct;
- forget.

No hidden irreversible memory.

---

# 36. Phase 4 Demo

User says:

> “Retiens que je préfère des rapports courts en français.”

Later:

> “Prépare un rapport.”

Expected: preference applied.

User can ask why.

---

# 37. Phase 4 Exit Gate

- memory survives sessions;
- explicit preference works;
- correction works;
- forget works;
- no cross-tenant leakage;
- context injection stays bounded.

---

# 38. Phase 5 — Skill/Tool Gateway

Goal:

No direct uncontrolled tool execution.

Implement:

```text
Skill Registry
Tool Gateway
Provider Adapter Interface
Permission checks
Risk metadata
Audit
Timeouts
Normalized errors
```

Start small.

---

# 39. Initial Skills

Implement/wrap:

```text
memory.retrieve
task.create
contact.resolve
file.read/write
```

Then external integrations.

---

# 40. Existing Integrations Migration

If Hermes already built direct integrations:

```text
Wrap
→ preserve behavior
→ route through Skill
→ add policy
→ migrate callers
```

Do not rewrite unless needed.

---

# 41. MCP Foundation

Implement MCP adapter/registry only if needed by selected MVP integrations.

Do not build public marketplace.

Support approved MCP servers only.

---

# 42. Agent Zero Foundation

Create interface/gateway.

Initial use:

```text
bounded research
```

Agent Zero is optional for MVP if integration risks schedule.

Do not block core product on it.

---

# 43. OfficeCLI Validation

Perform technical spike.

Deliver:

```text
docs/spikes/OFFICECLI_EVALUATION.md
```

Test:

```text
DOCX
XLSX
PPTX
formatting
latency
sandbox
licensing
```

Then decide.

---

# 44. Phase 5 Exit Gate

At least one real external capability executes:

```text
through Skill Registry
→ permission check
→ adapter
→ verification
→ audit
```

No direct bypass.

---

# 45. Phase 6 — Administrative Assistant MVP

Build high-value vertical slices.

Priority:

```text
1. Email triage/draft
2. Calendar/meeting preparation
3. Document generation
4. Tasks/commitments
5. Daily brief
```

---

# 46. Email MVP

Depending connected ecosystem:

```text
search/read
summarize
draft
send with approval
```

No bulk autonomy initially.

---

# 47. Calendar MVP

```text
read upcoming
create/update with approval
detect conflicts
```

---

# 48. Meeting Preparation

Command:

> “Prépare ma réunion de 15 heures.”

Combine:

```text
calendar
contacts
memory
email/files if available
```

Generate useful briefing.

---

# 49. Document Generation

Command:

> “Prépare une proposition pour Horizon.”

Generate actual artifact.

Use template/branding if configured.

Validate output.

---

# 50. Task/Commitment Tracking

Extract explicit tasks/commitments.

Show:

```text
Today
Waiting For
Upcoming
```

---

# 51. Daily Brief

Combine:

```text
Calendar
Important email
Tasks
Commitments
```

Keep concise.

---

# 52. Phase 6 Exit Gate

End-to-end demo:

> “Qu'est-ce qui mérite mon attention aujourd'hui ?”

and:

> “Prépare ma réunion avec Horizon.”

and:

> “Prépare cette proposition.”

At least one real artifact/action.

---

# 53. Phase 7 — Business Development MVP

This is a primary differentiator.

Implement:

```text
ICP
Prospect discovery
Research
Qualification
Scoring with evidence
Deduplication
Outreach drafting
Pipeline
```

---

# 54. Prospect Discovery

Use lawful/authorized sources.

Do not depend on scraping fragile sources without review.

Start with sources technically/legal operationally viable.

---

# 55. Qualification

Score based on explicit ICP.

Return reasons/evidence.

Do not fabricate revenue/headcount.

Use unknown when unavailable.

---

# 56. Prospect List UX

Show:

```text
Company
Why it fits
Evidence
Score/confidence
Suggested angle
```

Quality over volume.

---

# 57. Outreach

Generate personalized drafts.

Initial default:

```text
draft only
```

Sending requires approval.

---

# 58. Suppression

Before outreach:

- existing customers;
- duplicates;
- opt-outs;
- excluded contacts.

Mandatory.

---

# 59. Phase 7 Demo

User:

> “Trouve-moi 10 prospects sérieux au Togo pour mon activité.”

EMEFA:

- uses business profile;
- researches;
- qualifies;
- returns evidence;
- prepares selected messages.

This is a flagship demo.

---

# 60. Phase 7 Exit Gate

At least:

- prospect discovery works;
- qualification evidence visible;
- dedupe;
- outreach drafts;
- no unauthorized sends.

---

# 61. Phase 8 — Durable Workflows & Autonomy

Only after core Skills work.

Implement:

```text
Task/run persistence
Background workers
Schedules
Approvals
Retries
Cancellation
Budgets
Notifications
```

Start with 2 workflows.

---

# 62. Workflow 1 — Weekly Prospecting

```text
Weekly trigger
→ find prospects
→ qualify
→ prepare drafts
→ notify
→ wait for send approval
```

---

# 63. Workflow 2 — Morning Brief

```text
Weekday trigger
→ calendar
→ emails
→ tasks
→ commitments
→ concise brief
```

---

# 64. Durable State

Workflow must survive:

```text
app closed
server restart
network failure
```

No in-memory-only scheduler.

---

# 65. Approval Inbox

Implement minimum:

```text
Preview
Approve
Reject
```

For email sends/actions.

---

# 66. Kill Switch

Implement:

```text
Pause Autonomous Actions
```

Before enabling recurring autonomous work.

---

# 67. Phase 8 Exit Gate

User configures:

> “Chaque semaine, trouve-moi 10 prospects, mais demande avant d'envoyer.”

It runs in background and reaches approval state correctly.

---

# 68. Phase 9 — Integrated Demo Experience

Now polish the product story.

The demo should feel like one assistant, not disconnected features.

---

# 69. Demo Narrative

Recommended:

## Scene 1 — Morning

> “Bonjour EMEFA, qu'est-ce qui mérite mon attention ?”

Assistant gives brief.

## Scene 2 — Administrative

> “Prépare ma réunion avec Horizon.”

Brief appears.

## Scene 3 — Document

> “Prépare la proposition.”

Artifact created.

## Scene 4 — Growth

> “Trouve-moi 10 nouveaux prospects.”

Prospects appear with evidence.

## Scene 5 — Autonomy

> “Fais ça chaque semaine, mais demande avant d'envoyer.”

Workflow created.

---

# 70. JARVIS Experience

Use 3D UI purposefully:

- listening animation;
- tool/work indicators;
- result cards;
- approvals;
- artifact previews.

Avoid decorative overload that slows interaction.

---

# 71. Perceived Intelligence

EMEFA should demonstrate:

```text
Memory
Context
Action
Continuity
```

Not just eloquent conversation.

---

# 72. Demo Data

Use realistic synthetic/demo business.

Do not expose real customer/private data.

Prepare deterministic demo mode if external services unreliable.

---

# 73. Demo Resilience

Have:

```text
live path
+
mock/fallback path
```

A provider outage should not destroy investor/customer demo.

Clearly distinguish mocks in development; do not misrepresent fake execution as live in production.

---

# 74. Phase 9 Exit Gate

A new observer can understand EMEFA's value within ~5 minutes.

They should see:

```text
It understands my business
It remembers
It acts
It finds opportunities
It works in background
It asks permission appropriately
```

---

# 75. Phase 10 — Hardening

Before production pilot:

```text
Security review
Performance
Cost review
Error UX
Backup/restore
Monitoring
Rate limits
Provider failure handling
Tenant isolation tests
Prompt injection tests
```

---

# 76. Performance Targets

Define measured targets after baseline.

Track:

```text
time to first voice response
tool latency
workflow completion
page load
3D rendering impact
```

Optimize based on profiling.

---

# 77. Cost Targets

Track per tenant/task:

```text
LLM
STT
TTS
search/enrichment
Agent Zero
storage
compute
```

No hidden economics.

---

# 78. Voice Cost Strategy

Benchmark alternatives.

Potential architecture may combine:

```text
LiveKit for realtime transport
+
lower-cost STT/TTS providers
+
premium fallback/optional voices
```

Exact providers must be selected based on current quality/cost tests.

Do not assume LiveKit itself replaces STT/TTS.

---

# 79. Model Routing

Use premium model only where needed.

Potential:

```text
Fast/cheap model → classification/extraction
Strong model → complex planning/writing
Embedding model → retrieval
```

Do not overcomplicate before measurement.

---

# 80. Production Pilot

Start with small controlled group.

Ideal:

```text
5–20 entrepreneurs/SMEs
```

Observe:

- what they delegate;
- what they repeat;
- where trust fails;
- what saves time;
- whether prospecting produces useful leads.

---

# 81. Pilot Metrics

Core:

```text
Weekly active assistants
Tasks completed
Administrative time saved estimate
Prospects qualified
Outreach approved
Meetings/opportunities generated
User correction rate
Workflow recurrence
Retention
Cost per active user
```

---

# 82. Product-Market Learning

Do not add features based only on imagination.

After pilot, prioritize repeated pain.

Potential strongest wedges:

```text
Prospecting
Administrative follow-up
Documents
Email/calendar
WhatsApp/business communication
```

Measure.

---

# 83. Deferred Scope

Explicitly NOT required before MVP:

```text
Public Skill marketplace
Hundreds of MCPs
Full ERP
Full accounting suite
Every African language
Perfect voice cloning
Universal computer control
Unlimited Agent Zero autonomy
Mobile apps for every platform
Enterprise multi-region deployment
```

Architecture may allow them later.

Do not build now.

---

# 84. Scope Change Rule

New idea discovered during implementation:

Ask:

```text
Is it required for current phase exit criteria?
```

If no:

```text
add to BACKLOG.md
continue current phase
```

This prevents endless expansion.

---

# 85. Backlog

Maintain:

```text
docs/BACKLOG.md
```

Sections:

```text
Now
Next
Later
Research
```

Do not create architecture documents for every backlog item.

---

# 86. Engineering Work Log

Maintain concise:

```text
docs/IMPLEMENTATION_STATUS.md
```

Include:

```text
Current phase
Completed
In progress
Blocked
Next
Decisions
```

Update after meaningful milestones.

---

# 87. Commit Discipline

Prefer small coherent commits.

Examples:

```text
feat(memory): add explicit preference persistence
feat(skills): add governed email send skill
fix(auth): enforce tenant scope on workflow query
```

Do not create giant unreviewable changes.

---

# 88. Migration Discipline

Database changes:

- migrations;
- reversible where possible;
- no manual production drift.

Never drop existing Hermes data casually.

---

# 89. Test Pyramid

Use:

```text
Unit
Integration
Contract
E2E
```

High-risk flows require E2E.

---

# 90. Mandatory E2E Scenarios

At minimum:

```text
Onboarding persists
Memory preference recalled
Voice/text context continuity
Email draft + approval
Meeting preparation
Document generation
Prospect discovery/qualification
Scheduled workflow reaches approval
Tenant isolation
```

---

# 91. Security Tests

Mandatory:

```text
Cross-tenant access
Unauthorized Skill
Approval bypass
Prompt injection escalation
Path traversal
Secret leakage
Webhook replay if used
Duplicate send retry
```

---

# 92. AI Evaluation

Maintain eval cases for:

```text
Intent resolution
Memory retrieval
Prospect qualification
Email drafting
Meeting briefing
Tool selection
Prompt injection resistance
```

Model changes should run evals.

---

# 93. Do Not Chase 100% Autonomy

MVP trust model:

```text
EMEFA reads/prepares broadly
EMEFA executes low-risk configured actions
EMEFA asks before consequential external actions
```

Increase autonomy after evidence.

---

# 94. Definition of MVP Complete

MVP is complete when a pilot user can:

```text
1. Create/configure EMEFA
2. Explain business once
3. Talk naturally by voice/text
4. Have preferences remembered
5. Connect at least core work tools
6. Get administrative assistance
7. Generate a real business document
8. Find and qualify prospects
9. Prepare outreach
10. Configure at least one recurring workflow
11. Review/approve consequential actions
12. Return later and continue with preserved context
```

Not when every future feature exists.

---

# 95. Claude Working Rule

At each phase:

```text
1. Read relevant specifications
2. Inspect existing implementation
3. State implementation plan
4. Implement smallest coherent slice
5. Run tests/lint/typecheck/build
6. Fix regressions
7. Update status
8. Commit/prepare clear diff
9. Move only when exit criteria pass
```

---

# 96. When Claude Encounters Ambiguity

Claude should:

1. inspect code/docs first;
2. infer only reversible low-risk details;
3. document assumption;
4. ask user only when decision materially affects product/security/data.

Do not block on trivial questions.

---

# 97. When Existing Code Conflicts With Specs

Classify:

```text
Existing code better/valid → retain and document
Spec is target but migration risky → incremental migration
Existing code unsafe → prioritize correction
Spec assumption wrong → create ADR/update implementation note
```

Specs guide architecture; reality of code must be inspected.

---

# 98. No Blind Dependency Installation

Before adding package:

```text
Can existing dependency do it?
Is package maintained?
License acceptable?
Security?
Bundle/runtime impact?
```

Avoid dependency bloat.

---

# 99. No Blind Rewrite

Do not rewrite:

```text
UI
3D system
authentication
database
voice
```

merely because Claude prefers another stack.

Replacement requires evidence.

---

# 100. Handoff to Hermes / DevOps

After Claude implementation:

Hermes may handle:

```text
deployment
infrastructure tuning
environment setup
CI/CD refinements
monitoring
production fixes
```

Claude must leave:

```text
README
.env.example
migration instructions
deployment notes
test commands
architecture notes
known limitations
```

---

# 101. Final Delivery Package

Before handoff:

```text
Working repository
Migrations
Tests
Documentation
Architecture decisions
Implementation status
Backlog
Deployment guide
Security checklist
Demo script
Known issues
```

---

# 102. The Three Product Proofs

Before expanding, EMEFA must prove three things:

## Proof 1 — Understand

> EMEFA understands the user's business and remembers useful context.

## Proof 2 — Act

> EMEFA completes real administrative work through tools.

## Proof 3 — Grow

> EMEFA helps find and advance real business opportunities.

If these three work, the platform thesis is credible.

---

# 103. The MVP Flywheel

```text
Onboarding
→ Understanding
→ Useful Work
→ Memory
→ Better Personalization
→ More Delegation
→ More Value
```

Business development adds:

```text
Prospecting
→ Opportunities
→ Outcomes
→ Learning
→ Better Prospecting
```

---

# 104. STOP CONDITION

After this roadmap:

There is exactly **ONE** remaining mandatory planning artifact:

```text
CLAUDE_EXECUTION_PROMPT.md
```

After that file is created:

```text
STOP WRITING ARCHITECTURE DOCUMENTS.
```

The next action must be:

```text
Give Claude:
- existing EMEFA repository
- specification files
- CLAUDE_EXECUTION_PROMPT.md

Then begin Phase 0 repository audit.
```

Any new feature idea goes to:

```text
docs/BACKLOG.md
```

unless it blocks an MVP exit criterion.

---

# 105. Final Principle

> **The objective is not to finish imagining EMEFA. The objective is to start shipping EMEFA.**

Implementation order:

```text
Understand Existing Work
→ Stabilize Foundations
→ Preserve Product Identity
→ Build Core Intelligence
→ Connect Real Tools
→ Deliver Administrative Value
→ Deliver Business Growth Value
→ Add Bounded Autonomy
→ Test With Real Users
→ Learn
→ Iterate
```

Do not restart.

Do not endlessly document.

Do not build the entire future before validating the present.

Build the smallest version of the full vision that makes an entrepreneur say:

> “Cette assistante comprend mon activité, travaille réellement pour moi, et m'aide à faire avancer mon entreprise.”
