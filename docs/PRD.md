# EMEFA — PRD.md

> **Document type:** Product Requirements Document  
> **Project:** EMEFA  
> **Status:** Foundational requirements specification  
> **Development mode:** Brownfield continuation of the existing EMEFA implementation initiated by Hermes  
> **Primary engineering agent:** Claude  
> **Rule:** This PRD defines product requirements. Actual implementation sequencing must be reconciled with `CURRENT_STATE_ASSESSMENT.md`.

---

# 1. Product Summary

EMEFA is a personalized AI executive-assistant platform for entrepreneurs, executives, SMEs, and organizations.

EMEFA must progressively:

- understand the user and their business;
- maintain useful and controllable memory;
- communicate through text and natural realtime voice;
- use authorized tools and skills;
- perform administrative work;
- create professional business artifacts;
- help continuously create business opportunities;
- execute recurring/proactive work within explicit permissions;
- verify outcomes;
- become more useful through legitimate personalization.

EMEFA is not a chatbot.

The product model is:

```text
Understand
→ Remember
→ Plan
→ Act
→ Verify
→ Learn Relevant Preferences
```

---

# 2. Product Goals

## G1 — Reduce Administrative Burden

EMEFA should complete or prepare repetitive executive/administrative work.

## G2 — Help Create Business Opportunities

EMEFA should support continuous prospecting, qualification, follow-up, and commercial preparation.

## G3 — Reduce Interaction Friction

Users should delegate naturally through voice or text.

## G4 — Build Compounding Personalization

EMEFA should become more useful as it learns approved context, preferences, and workflows.

## G5 — Remain Extensible

New capabilities should be added through Skills, APIs, MCP, CLIs, workflows, browser/computer use, or controlled external agents.

## G6 — Build African Differentiation

The architecture must support African languages, accents, code-switching, local workflows, and regional integrations.

## G7 — Preserve Human Control

Consequential actions must remain permissioned, visible, auditable, and revocable.

---

# 3. Non-Goals for Initial Product

The initial product does NOT need to:

- replace every SaaS application;
- autonomously run an entire company;
- support every African language at launch;
- provide unrestricted autonomous internet/computer access;
- implement a large public skill marketplace immediately;
- use multiple agents for every task;
- eliminate all human approvals;
- perfectly imitate JARVIS;
- rebuild working Hermes functionality without evidence.

---

# 4. Primary Users

## Persona A — Entrepreneur / Founder

Pain:

- too many responsibilities;
- insufficient administrative support;
- inconsistent follow-up;
- customer acquisition pressure.

Desired outcome:

> “Help me handle the work that steals my time and help me create more opportunities.”

## Persona B — SME Director

Pain:

- fragmented information;
- meeting overload;
- reporting;
- coordination;
- decisions dependent on manual preparation.

Desired outcome:

> “Give me a reliable executive assistant that already understands the company.”

## Persona C — Commercially Focused Owner

Pain:

- prospecting inconsistency;
- weak follow-up;
- time-consuming research;
- lost leads.

Desired outcome:

> “Keep helping me build pipeline while I run the business.”

## Persona D — Consultant / Professional

Pain:

- proposals;
- scheduling;
- client communication;
- research;
- documents.

Desired outcome:

> “Know how I work and handle repeatable client-facing tasks.”

---

# 5. Core User Journey

```text
Discover EMEFA
      ↓
Create Account / Workspace
      ↓
Meet EMEFA
      ↓
Conversational Onboarding
      ↓
EMEFA Builds Business Context
      ↓
Connect Skills / Tools
      ↓
Set Permissions
      ↓
Delegate First Real Task
      ↓
Review / Approve if Needed
      ↓
EMEFA Executes
      ↓
EMEFA Verifies
      ↓
Result Delivered
      ↓
Relevant Preference / Context Learned
      ↓
Recurring Use / Proactivity
```

The first-value journey must not require configuring every possible integration.

---

# 6. Requirement Priority Labels

Use:

- **P0** — required for safe core product operation;
- **P1** — required for compelling MVP/value;
- **P2** — important next-stage capability;
- **P3** — later expansion.

Implementation order may differ based on the current-state audit.

---

# 7. Account and Workspace

## FR-001 — User Account

**Priority:** P0

Users must have authenticated identities.

Acceptance criteria:

- authentication is server-validated;
- sessions are secure;
- unauthorized access is rejected;
- no secrets are exposed to the client unnecessarily.

## FR-002 — Organization / Workspace

**Priority:** P0/P1 depending on existing implementation

A user must operate within an organization/workspace boundary.

Acceptance criteria:

- persistent resources have ownership;
- cross-tenant access is prevented;
- backend authorization does not trust client-provided tenant identity alone.

## FR-003 — Assistant Identity

**Priority:** P1

Each assistant instance should have configurable identity attributes such as:

- name;
- personality configuration;
- voice configuration;
- language preferences;
- organizational context.

EMEFA remains the default product identity.

---

# 8. Conversational Onboarding

## FR-010 — Adaptive Onboarding Conversation

**Priority:** P1

EMEFA must conduct a natural onboarding conversation.

It should learn progressively:

- user's role;
- organization;
- industry;
- products/services;
- business model;
- target customers;
- markets;
- team;
- goals;
- recurring workflows;
- communication preferences;
- document standards;
- tools;
- languages;
- autonomy preferences.

Acceptance criteria:

- questions adapt to previous answers;
- known information is not repeatedly requested;
- user can skip/defer questions;
- partial onboarding still allows useful work;
- extracted information becomes structured context.

## FR-011 — Business Profile

**Priority:** P1

Create a structured organization/business profile.

Example domains:

```text
Company
Offer
Customers
Markets
Team
Brand
Processes
Goals
Constraints
```

Users must eventually be able to review/correct relevant profile information.

## FR-012 — Progressive Onboarding

**Priority:** P1

EMEFA may ask context-building questions later when required for a task.

Do not force exhaustive setup before first value.

---

# 9. Conversation

## FR-020 — Text Interaction

**Priority:** P0

Users must be able to interact with EMEFA through text.

Requirements:

- conversation state;
- clear response status;
- errors shown honestly;
- support for task/action results.

## FR-021 — Realtime Voice

**Priority:** P1

Users must be able to speak naturally with EMEFA.

Requirements:

- low perceived latency;
- interruption/barge-in;
- progressive transcript where appropriate;
- clear microphone/session state;
- graceful permission errors;
- reconnect/failure handling.

Existing working voice behavior must be preserved during migration.

## FR-022 — Voice Provider Flexibility

**Priority:** P1/P2

Architecture must support provider-swappable realtime/STT/TTS components.

ElevenLabs must not be removed until replacement is validated.

LiveKit should be benchmarked as a candidate realtime layer.

Acceptance criteria for migration:

- side-by-side benchmark exists;
- cost is documented;
- latency is documented;
- interruption is tested;
- mobile behavior is tested;
- rollback exists.

## FR-023 — Multimodal Continuity

**Priority:** P2

A task started by voice should be inspectable through visual/text UI.

Voice must not hide important action details.

---

# 10. Immersive Assistant Interface

## FR-030 — Assistant Presence

**Priority:** P1

EMEFA should maintain a distinctive immersive assistant presence.

The interface should communicate actual states such as:

```text
Idle
Listening
Understanding
Planning
Waiting for Approval
Executing
Verifying
Completed
Warning
Failed
```

## FR-031 — 3D / Motion

**Priority:** P1/P2

Preserve and improve existing high-quality 3D/motion work when appropriate.

Requirements:

- visuals map to real state;
- mobile performance;
- reduced-motion support;
- graceful fallback;
- no obstruction of productive workflows.

## FR-032 — JARVIS-Class Experience

**Priority:** Product principle

Aim for immediacy, fluidity, spatial presence, and contextual intelligence associated with advanced fictional assistants.

Do not copy protected character identity, voice, dialogue, or audiovisual assets.

---

# 11. Memory

## FR-040 — User Profile Memory

**Priority:** P1

Store durable user context where appropriate.

Examples:

- preferred communication style;
- role;
- working preferences.

## FR-041 — Organization Memory

**Priority:** P1

Store structured business context.

## FR-042 — Preference Memory

**Priority:** P1

Example:

> “Our proposals should normally be under five pages.”

Future relevant tasks should apply the preference.

## FR-043 — Episodic Memory

**Priority:** P2

Store useful summaries of meaningful past interactions/work.

Do not store all raw conversation indefinitely by default.

## FR-044 — Memory Control

**Priority:** P1/P2

Users should be able to:

- inspect;
- correct;
- delete;
- eventually export relevant memory.

## FR-045 — Memory Provenance

**Priority:** P1/P2

Important memory should track source/provenance where feasible.

## FR-046 — Memory Isolation

**Priority:** P0

Memory must be tenant/user scoped.

---

# 12. Skills

## FR-050 — Skill Registry

**Priority:** P1

EMEFA must have a controlled registry of capabilities.

A Skill should expose where applicable:

- ID;
- version;
- description;
- provider;
- schemas;
- permissions;
- risk;
- confirmation policy;
- health;
- verification strategy.

## FR-051 — Skill Enable/Disable

**Priority:** P1

Users/admins should be able to enable or disable appropriate skills.

## FR-052 — Skill Permissions

**Priority:** P0/P1

Skills must not execute outside authorized scopes.

## FR-053 — Skill Health

**Priority:** P2

EMEFA should know when a skill/integration is unavailable.

---

# 13. MCP

## FR-060 — MCP Integration Layer

**Priority:** P2

EMEFA should support MCP servers through a controlled integration layer.

Requirements:

- configuration;
- discovery;
- schema validation;
- credentials;
- permission mapping;
- audit;
- timeouts;
- health.

## FR-061 — MCP Trust Boundary

**Priority:** P0 when MCP is enabled

MCP output is untrusted data.

MCP content cannot override EMEFA system policy or user permissions.

---

# 14. External Agent Gateway

## FR-070 — Specialist Agent Delegation

**Priority:** P2

EMEFA may delegate specialized tasks to systems such as Agent Zero.

Requirements:

- bounded task contract;
- minimum necessary context;
- permissions;
- timeout;
- budget;
- cancellation where possible;
- result validation;
- audit.

## FR-071 — EMEFA Remains Orchestrator

**Priority:** P0 principle

External agents must not become the user's runtime identity or bypass EMEFA control.

---

# 15. Administrative Assistant Capabilities

## FR-100 — Email Assistance

**Priority:** P1

Capabilities may include:

- search/read authorized email;
- summarize;
- prioritize;
- draft replies;
- prepare follow-ups;
- send only according to permission policy.

Acceptance criteria:

- outbound communication follows approval policy;
- recipients/content are shown before approval when required;
- send result is verified.

## FR-101 — Calendar

**Priority:** P1

Capabilities:

- inspect schedule;
- find availability;
- prepare meetings;
- create/update events according to permission;
- detect conflicts.

## FR-102 — Meeting Preparation

**Priority:** P1

Given a meeting, EMEFA should gather authorized context and prepare:

- objective;
- participants;
- relevant history;
- open issues;
- documents;
- suggested questions/actions.

## FR-103 — Meeting Follow-Up

**Priority:** P2

EMEFA should turn meeting information into:

- summary;
- decisions;
- action items;
- follow-ups.

## FR-104 — Task / Commitment Tracking

**Priority:** P1/P2

Track relevant commitments:

- owner;
- due date;
- status;
- source.

Surface overdue/at-risk items.

## FR-105 — Executive Morning Brief

**Priority:** P1 Hero Workflow

User asks:

> “EMEFA, qu'est-ce qui demande mon attention aujourd'hui ?”

EMEFA synthesizes authorized:

- schedule;
- important messages;
- commitments;
- tasks;
- commercial follow-ups.

Acceptance criteria:

- concise prioritized output;
- evidence/source references where useful;
- no invented obligations;
- actionable next steps.

---

# 16. Office and Document Capabilities

## FR-120 — Professional Document Creation

**Priority:** P1

EMEFA must create professional documents from business context.

Examples:

- proposals;
- letters;
- reports;
- quotations;
- briefs.

## FR-121 — Word/DOCX

**Priority:** P1

Support creation/editing through a provider abstraction.

OfficeCLI is a candidate provider.

## FR-122 — Spreadsheet/XLSX

**Priority:** P1/P2

Support:

- workbook creation;
- formatting;
- formulas where appropriate;
- data analysis;
- summaries.

## FR-123 — Presentation/PPTX

**Priority:** P2

Support professional presentations.

## FR-124 — Branding and Templates

**Priority:** P1/P2

Use organization standards:

- logo;
- fonts;
- colors;
- layout;
- standard sections;

when available and authorized.

## FR-125 — Document Verification

**Priority:** P1

Validate generated artifacts.

Where feasible:

- structural validation;
- open/render check;
- visual inspection;
- formula/reference checks.

Never claim a document is ready if generation failed.

---

# 17. Business Development

This is a primary product pillar.

## FR-200 — Offer Understanding

**Priority:** P1

EMEFA must understand:

- what the company sells;
- value proposition;
- differentiators;
- geography;
- constraints.

## FR-201 — Ideal Customer Profile

**Priority:** P1

Create structured ICP(s):

- industry;
- company size;
- geography;
- role;
- pain;
- buying signals;
- exclusions.

Users can correct the model.

## FR-202 — Prospect Discovery

**Priority:** P1 Hero Capability

Find potential prospects from authorized/lawful sources.

Requirements:

- source provenance;
- duplicate control;
- filtering;
- relevance.

## FR-203 — Prospect Research

**Priority:** P1

Research:

- company;
- activity;
- fit;
- relevant signals;
- contact context where lawfully available.

## FR-204 — Qualification

**Priority:** P1

Score/classify prospects using transparent criteria.

Do not present probabilistic qualification as fact.

## FR-205 — Personalized Outreach Preparation

**Priority:** P1

Prepare relevant outreach based on:

- prospect;
- offer;
- channel;
- business context.

Avoid generic mass spam.

## FR-206 — Outreach Approval

**Priority:** P0/P1

Outbound communication must follow permission policy.

Support:

- draft only;
- approval required;
- scoped automatic sending.

## FR-207 — Follow-Up

**Priority:** P1

Track:

- last contact;
- response;
- next action;
- due date.

## FR-208 — Pipeline

**Priority:** P1/P2

Maintain structured prospect/opportunity state.

## FR-209 — Opportunity Recommendations

**Priority:** P2

Surface next-best commercial actions.

## FR-210 — Prospecting Brief

**Priority:** P1 Hero Workflow

User:

> “Trouve-moi de nouvelles entreprises qui correspondent à notre cible.”

Expected flow:

```text
Load business context
→ Load ICP
→ Discover
→ Deduplicate
→ Research
→ Qualify
→ Explain fit
→ Prepare next actions
→ Ask approval where required
→ Persist pipeline state
```

---

# 18. Proactivity

## FR-250 — Proactive Suggestions

**Priority:** P2

EMEFA may surface useful issues/opportunities.

Examples:

- overdue follow-up;
- upcoming meeting lacking preparation;
- unanswered important message;
- prospect requiring action.

## FR-251 — Recurring Work

**Priority:** P2

Users may authorize recurring workflows.

Examples:

- morning brief;
- weekly prospecting;
- weekly report.

## FR-252 — Conditional Work

**Priority:** P2/P3

Users may authorize conditional workflows.

Example:

> “When a qualified prospect replies positively, alert me and prepare meeting options.”

Requires durable workflow/event architecture.

## FR-253 — Proactivity Controls

**Priority:** P1/P2

Users can:

- configure;
- pause;
- cancel;
- inspect;
- revoke proactive behavior.

---

# 19. Permissions and Autonomy

## FR-300 — Autonomy Levels

**Priority:** P0/P1

Support conceptual levels:

1. Suggest.
2. Prepare.
3. Execute after approval.
4. Execute within scoped policy.
5. Proactive execution within scoped policy.

## FR-301 — Risk Classification

**Priority:** P0

Actions must be classified.

At minimum:

- read-only;
- reversible write;
- external communication;
- destructive;
- financial/legal/security-sensitive.

## FR-302 — Confirmation

**Priority:** P0

High-risk actions require stronger confirmation.

## FR-303 — Scoped Authorization

**Priority:** P1

Authorization may be:

- one-time;
- session;
- persistent scoped policy.

## FR-304 — Revocation

**Priority:** P1

Users can revoke persistent permissions.

---

# 20. Execution and Verification

## FR-320 — Explicit Task State

**Priority:** P0/P1

Use honest states:

```text
PLANNED
PREPARED
AWAITING_APPROVAL
EXECUTING
QUEUED
PARTIALLY_COMPLETED
COMPLETED
VERIFIED
FAILED
CANCELLED
```

## FR-321 — Verification

**Priority:** P0/P1

Where feasible, verify:

- sent message exists;
- event exists;
- file opens;
- record changed;
- prospect saved;
- workflow completed.

## FR-322 — No Fake Completion

**Priority:** P0

Attempted action ≠ completed action.

---

# 21. African Languages

## FR-400 — Language Architecture

**Priority:** P1 architecture / P2 product

Support provider-swappable:

- language detection;
- STT;
- LLM;
- TTS.

## FR-401 — French

**Priority:** P1

Strong French interaction is required for initial target users.

## FR-402 — Local Language Evaluation

**Priority:** P2

Research/evaluate languages relevant to initial market, potentially:

- Ewe;
- Kabiye;
- Mina/related varieties.

Do not claim production support before testing.

## FR-403 — Code-Switching

**Priority:** P2

Evaluate natural switching between French and supported local languages.

## FR-404 — Local Language Task Completion

**Priority:** P2

Success means more than transcription.

A user must be able to request a real task and receive a correct outcome.

---

# 22. Notifications

## FR-450 — Action Notifications

**Priority:** P1/P2

Notify users when:

- approval required;
- task completed;
- task failed;
- important proactive event occurs.

Avoid excessive notifications.

---

# 23. Audit

## FR-500 — Action Audit

**Priority:** P0/P1

Record appropriate:

- actor;
- assistant;
- action;
- tool;
- permission;
- timestamp;
- result.

## FR-501 — User-Visible History

**Priority:** P1/P2

Users should inspect meaningful actions EMEFA performed.

---

# 24. Observability

## FR-520 — Technical Observability

**Priority:** P0/P1

Capture:

- errors;
- latency;
- model calls;
- tool calls;
- voice sessions;
- retries;
- approvals;
- costs where feasible.

Use correlation IDs.

Never log secrets unnecessarily.

---

# 25. Security Requirements

## SR-001 — Server-Side Authorization

All consequential authorization must be enforced server-side.

## SR-002 — Tenant Isolation

Persistent resources must be tenant scoped.

## SR-003 — Secrets

No hard-coded secrets.

## SR-004 — Least Privilege

Integrations receive minimum necessary scopes.

## SR-005 — Prompt Injection Defense

External content is data, not authority.

## SR-006 — Tool Safety

Validate:

- schemas;
- permissions;
- URLs;
- file paths;
- commands.

## SR-007 — External Agent Safety

Specialist agents cannot bypass EMEFA policy.

## SR-008 — MCP Safety

MCP output is untrusted.

## SR-009 — Auditability

Consequential actions must be reconstructable.

---

# 26. Non-Functional Requirements

## NFR-001 — Reliability

Critical workflows fail honestly and recover gracefully.

## NFR-002 — Performance

Voice and interactive flows should minimize perceived latency.

Targets must be established through baseline measurement.

## NFR-003 — Mobile

Core workflows must work well on modern mobile browsers.

## NFR-004 — Accessibility

Support:

- keyboard;
- semantic UI;
- reduced motion;
- non-voice alternatives.

## NFR-005 — Low Bandwidth

Graceful degradation should be considered for target markets.

## NFR-006 — Scalability

Architecture should support multi-tenant growth without premature complexity.

## NFR-007 — Maintainability

Use modular typed contracts and provider adapters.

## NFR-008 — Cost Efficiency

Track and optimize:

- voice;
- model;
- API;
- infrastructure costs.

---

# 27. Provider Strategy

EMEFA must avoid unnecessary provider lock-in.

Potential provider boundaries:

```text
LLMProvider
STTProvider
TTSProvider
RealtimeProvider
SearchProvider
EmailProvider
CalendarProvider
DocumentProvider
CRMProvider
ExternalAgentProvider
```

Do not abstract everything prematurely.

Abstract where strategic replacement or multiple providers are realistic.

---

# 28. ElevenLabs → Voice Architecture Evolution

Existing ElevenLabs behavior must remain until validated migration.

Required process:

```text
Baseline Current Voice
→ Introduce Boundaries
→ Prototype LiveKit / Alternatives
→ Benchmark
→ Compare Cost + Quality
→ Controlled Migration
→ Rollback Available
```

ElevenLabs may remain a premium TTS/voice option.

LiveKit is a candidate realtime layer, not automatically the entire speech stack.

---

# 29. Error Experience

EMEFA must communicate failures clearly.

Bad:

> “Done.”

when an API failed.

Good:

> “J'ai préparé le document, mais l'envoi a échoué. Le brouillon est conservé et je peux réessayer.”

Users need:

- what succeeded;
- what failed;
- what remains;
- what they can do next.

---

# 30. Hero Acceptance Scenarios

## Scenario A — Morning Brief

Given:

- connected calendar;
- relevant tasks;
- authorized communication access.

When user asks:

> “Qu'est-ce qui demande mon attention aujourd'hui ?”

Then EMEFA:

- retrieves authorized sources;
- prioritizes;
- avoids fabricated obligations;
- identifies actions;
- provides concise briefing.

## Scenario B — Proposal

When user asks:

> “Prépare une proposition pour Client X.”

Then EMEFA:

- identifies Client X;
- retrieves relevant company/client context;
- asks only necessary missing questions;
- generates professional document;
- applies known preferences/branding;
- verifies artifact;
- returns status and artifact.

## Scenario C — Prospecting

When user asks:

> “Trouve-moi 20 entreprises correspondant à notre cible.”

Then EMEFA:

- uses current ICP;
- uses authorized sources;
- finds candidates;
- removes duplicates;
- researches;
- qualifies;
- provides evidence;
- prepares next actions.

No outreach is sent without applicable authorization.

## Scenario D — Learned Preference

User says:

> “À l'avenir, fais mes propositions courtes, maximum cinq pages.”

Then:

- preference is stored with appropriate scope;
- future proposal generation uses it;
- user can inspect/change it.

## Scenario E — Voice Interruption

When EMEFA is speaking and user interrupts:

- playback stops promptly;
- new speech is recognized;
- context remains coherent;
- assistant responds to new intent.

---

# 31. MVP Scope

Final MVP scope must be confirmed after current-state audit.

Target MVP should prove:

## Foundation

- authentication/workspace safety;
- basic assistant identity;
- audit;
- permission model.

## Experience

- text;
- reliable realtime voice;
- immersive existing UI preserved/elevated.

## Understanding

- conversational onboarding;
- structured business profile.

## Memory

- user/business/preferences.

## Skills

At least a small set of real integrations.

## Administrative Vertical Slice

At minimum one compelling end-to-end workflow such as:

- executive brief;
- meeting preparation;
- professional proposal.

## Business Development Vertical Slice

At minimum:

- ICP;
- prospect discovery;
- research;
- qualification;
- outreach preparation.

## Documents

Professional artifact generation.

## Trust

- approvals;
- verification;
- honest status.

---

# 32. Post-MVP

Likely:

- broader email/calendar automation;
- recurring workflows;
- deeper CRM;
- outbound prospecting automation;
- OfficeCLI expansion;
- Agent Zero gateway;
- MCP ecosystem;
- African local-language pilots;
- multi-assistant organizations;
- skill marketplace.

Do not treat this list as fixed roadmap order.

---

# 33. Product Analytics

Track meaningful events.

Examples:

```text
onboarding_started
onboarding_completed
business_profile_completed
skill_connected
task_started
task_completed
task_verified
task_failed
approval_requested
approval_granted
document_generated
prospect_qualified
outreach_prepared
voice_session_started
```

Avoid collecting unnecessary sensitive content.

---

# 34. Definition of MVP Success

The MVP succeeds if target users demonstrate:

1. They understand what EMEFA can do.
2. They can onboard without technical expertise.
3. EMEFA remembers useful business context.
4. They delegate real work.
5. At least one administrative workflow saves meaningful time.
6. Prospecting produces useful qualified opportunities.
7. Voice reduces interaction friction.
8. Users trust action/approval boundaries.
9. Users return because EMEFA has accumulated useful context.

---

# 35. Open Decisions Requiring Evidence

The following must not be guessed:

- exact primary database if not already settled;
- LiveKit adoption timing;
- default STT;
- default TTS;
- ElevenLabs long-term role;
- workflow engine;
- exact Agent Zero integration;
- initial local language;
- CRM priorities;
- first production prospect sources.

Resolve through:

- current-state audit;
- prototypes;
- benchmarks;
- user research;
- ADRs.

---

# 36. Engineering Handoff Rule

Claude must use this PRD together with:

- `README.md`;
- `CLAUDE.md`;
- `MASTER_GOAL.md`;
- `CURRENT_STATE_ASSESSMENT.md`;
- architecture/domain specifications.

Claude must not interpret this PRD as:

> “Implement every requirement immediately.”

Instead:

1. audit current state;
2. map existing capabilities to requirements;
3. identify gaps;
4. prioritize;
5. implement vertical slices;
6. validate each slice.

---

# 37. Final Product Requirement

EMEFA must ultimately create this user perception:

> **“This assistant understands how my business works. I can talk to it naturally. It remembers what matters. I can give it new capabilities. It handles real work. It helps me find opportunities. And I remain in control.”**

If EMEFA only talks intelligently, the product is incomplete.

If EMEFA only executes tools without understanding context, the product is incomplete.

If EMEFA looks futuristic but does not solve painful problems, the product is incomplete.

The product succeeds when:

> **Understanding + Memory + Execution + Opportunity Creation + Trust**

work together as one coherent assistant.
