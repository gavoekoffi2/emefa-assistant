# EMEFA — MASTER_GOAL.md

> **Document type:** Authoritative product end-state objective  
> **Project:** EMEFA  
> **Audience:** Claude, human engineering team, product leadership, architecture reviewers, future DevOps/maintenance agents  
> **Status:** Foundational specification  
> **Purpose:** Define what must ultimately be built, why it exists, the boundaries of the product, the required capabilities, and what “done” means at platform level.

---

# 0. Brownfield Continuation Mandate

EMEFA already has an existing implementation in the repository `gavoekoffi2/emefa-assistant`, created by a previous engineering agent. Claude MUST continue from that codebase rather than rebuilding from zero.

Before any major implementation or rewrite, Claude must:

1. audit the current repository and architecture;
2. identify what is working, incomplete, fragile, or costly;
3. preserve sound components and user-visible value;
4. refactor or replace only when technically justified;
5. produce `docs/CURRENT_STATE_ASSESSMENT.md`;
6. create a migration plan for any major subsystem replacement;
7. maintain rollback capability during migrations.

A rewrite is justified only by evidence such as security risk, severe architectural dead-end, unacceptable cost, reliability problems, maintainability failure, or inability to satisfy product requirements.

The existing product already includes a React/TypeScript PWA, FastAPI backend, real-time voice interaction, interruptibility, progressive transcription, bounded orchestration, risk policies, memory/audit foundations, and an allowlisted tool model. Claude must verify the exact current state from the repository before acting.

## 0.1 JARVIS-Class Experience

The interface should preserve and elevate EMEFA's immersive assistant identity. The target experience should evoke the immediacy, responsiveness, spatial intelligence, fluid motion, 3D visual feedback, natural spoken interaction, and sense of presence associated with advanced fictional assistants such as JARVIS — without copying copyrighted voice identities, protected audiovisual assets, dialogue, logos, or proprietary designs.

The objective is **JARVIS-class presence, not a JARVIS clone**.

The immersive visual layer must never become decorative “bling-bling” that harms usability, accessibility, latency, or business value.

## 0.2 Provider-Flexible Realtime Voice Architecture

The current ElevenLabs-based realtime voice experience is valuable, but the architecture must not depend permanently on one end-to-end voice vendor.

Target voice architecture:

`Microphone → realtime transport/session → VAD/turn detection → STT → EMEFA orchestration/tools → TTS → streamed audio`

A framework such as LiveKit may be adopted as the realtime transport/agent-session layer, provided migration is benchmarked and does not degrade the current experience.

STT and TTS must be provider-swappable through adapters.

ElevenLabs may remain available as a premium TTS/voice option rather than being the mandatory runtime.

Before replacing the current voice path, benchmark side-by-side:

- end-to-end latency and time-to-first-audio;
- interruption/barge-in quality;
- transcription accuracy;
- African accent and local-language performance;
- voice naturalness;
- mobile/browser stability;
- concurrency;
- cost per active voice minute;
- privacy and retention;
- operational complexity.

Do not remove the working ElevenLabs integration until the replacement passes acceptance tests and rollback exists.

---


# 0A. Required First Engineering Deliverable

Before broad implementation, Claude must inspect the actual repository and produce:

`docs/CURRENT_STATE_ASSESSMENT.md`

This assessment must reconcile the existing implementation with this Master Goal and classify major subsystems as:

- KEEP;
- KEEP + HARDEN;
- REFACTOR;
- MIGRATE;
- REPLACE;
- REMOVE;
- UNKNOWN / REQUIRES BENCHMARK.

No major subsystem should be marked `REPLACE` without evidence and a migration/rollback plan.

This current-state assessment becomes the bridge between Hermes's existing work and Claude's continuation work.

---

# 1. Master Goal

Build **EMEFA**, a production-grade platform that enables entrepreneurs, executives, SMEs, and organizations to create their own deeply personalized AI executive assistant.

Each EMEFA assistant must be capable of progressively:

1. understanding the user and their organization;
2. learning how they work;
3. maintaining useful and controllable memory;
4. communicating naturally through text and voice;
5. understanding business goals and operational context;
6. using tools and specialized skills;
7. executing authorized administrative and business tasks;
8. coordinating external agents and services when useful;
9. verifying the outcome of its actions;
10. operating proactively within explicit user-defined boundaries;
11. helping the user save time, reduce operational friction, and create business opportunities;
12. becoming more useful through legitimate personalization over time.

EMEFA must begin with strong relevance to African entrepreneurs and SMEs while remaining architecturally capable of serving global markets.

The final product must not be a chatbot demo.

It must be an **operational AI assistant platform**.

---

# 2. Product Promise

The long-term user promise is:

> **Create an AI assistant that understands your business and actually works with you.**

A stronger operational interpretation is:

> **Tell EMEFA what matters. Connect the tools you authorize. EMEFA helps execute the work.**

The system must move beyond answering questions.

The target execution model is:

```text
User Intent
    ↓
Understand Context
    ↓
Retrieve Relevant Memory
    ↓
Determine Required Outcome
    ↓
Plan if Necessary
    ↓
Select Skills / Tools / Agents
    ↓
Check Permissions & Risk
    ↓
Execute
    ↓
Verify
    ↓
Report Outcome
    ↓
Update Relevant State / Memory / Audit
```

---

# 3. Strategic Product Identity

EMEFA is simultaneously:

- an AI executive assistant;
- an administrative work executor;
- a business-development assistant;
- a personalized business context engine;
- an agent orchestration platform;
- a skill/tool execution platform;
- eventually, a platform for creating many specialized assistants.

EMEFA is **not**:

- merely a conversational UI;
- a clone of ChatGPT;
- a clone of Jarvis;
- a voice skin over an LLM;
- a wrapper around Claude;
- a wrapper around Hermes;
- a wrapper around Agent Zero;
- a single autonomous loop with unrestricted tools;
- a collection of brittle automation scripts;
- a generic “AI employee” marketing demo without measurable workflows.

---

# 4. Primary Target Users

## 4.1 Initial Target

The initial commercial focus is:

- entrepreneurs;
- founders;
- business owners;
- SME/SMI executives;
- directors and managers;
- professionals who need executive-assistant capacity but cannot or do not want to build a large administrative team.

The initial geographic/product-learning focus should strongly consider African markets and realities.

## 4.2 Future Expansion

The architecture must support future expansion toward:

- larger organizations;
- teams;
- departments;
- professional services;
- industry-specific assistants;
- enterprise deployments;
- assistant/skill ecosystems.

---

# 5. The Core Problems EMEFA Must Solve

EMEFA should prioritize painful, recurring, economically meaningful problems.

## 5.1 Administrative Overload

Leaders spend too much time on:

- email;
- scheduling;
- document preparation;
- follow-ups;
- reports;
- presentations;
- spreadsheets;
- meeting preparation;
- action tracking;
- repetitive coordination.

EMEFA must reduce this burden.

## 5.2 Customer Acquisition

Many entrepreneurs continuously face the problem:

> “Where will my next customers come from?”

EMEFA must include business-development capabilities that help users:

- identify opportunities;
- research prospects;
- qualify prospects;
- prepare personalized outreach;
- manage follow-up;
- maintain pipeline visibility;
- prepare commercial materials;
- identify next actions.

This is a **priority product pillar**, not a secondary add-on.

## 5.3 Fragmented Software

Businesses often operate across many disconnected tools.

EMEFA should become a unified conversational/action layer over authorized systems.

The user should not need to understand which internal tool is used for every task.

They express intent.

EMEFA coordinates execution.

## 5.4 Lack of Context in Existing AI

Generic assistants repeatedly require users to explain:

- who they are;
- what their company does;
- who their customers are;
- their preferences;
- their workflows;
- their team;
- their brand;
- their goals.

EMEFA must build persistent, controllable context so usefulness compounds over time.

---

# 6. Foundational User Journey

A production EMEFA experience should eventually support the following lifecycle.

## Step 1 — Create Assistant

The user creates an EMEFA instance.

They choose or configure:

- assistant name;
- language;
- voice;
- personality style;
- initial role;
- autonomy preferences.

## Step 2 — Conversational Discovery

EMEFA conducts a structured but natural interview.

It learns:

- user identity and role;
- company;
- industry;
- products/services;
- business model;
- target customers;
- markets;
- team;
- workflows;
- recurring tasks;
- objectives;
- constraints;
- communication preferences;
- tools;
- approval preferences;
- brand/document standards.

The onboarding must adapt based on previous answers.

It must not feel like a static 100-field form.

## Step 3 — Build Business Context

The system converts onboarding information into structured context.

Examples:

```text
User Profile
Organization Profile
Products & Services
Ideal Customer Profiles
Team / Relationships
Preferences
Objectives
Recurring Workflows
Policies
Brand Guidelines
Connected Systems
```

## Step 4 — Connect Capabilities

The user connects approved tools and skills.

Examples:

- email;
- calendar;
- contacts;
- cloud files;
- office documents;
- CRM;
- accounting/business software;
- messaging;
- research/web;
- browser automation;
- MCP servers;
- specialized agents.

## Step 5 — Define Autonomy

The user chooses what EMEFA may:

- read;
- prepare;
- modify;
- send;
- execute;
- automate.

Permissions must be scoped.

## Step 6 — Work Together

The user begins delegating tasks.

EMEFA retrieves relevant context and executes within permissions.

## Step 7 — Learn

The user:

- approves;
- rejects;
- corrects;
- teaches;
- adds knowledge;
- installs skills.

EMEFA becomes better aligned.

## Step 8 — Become Proactive

Once trust and permissions exist, EMEFA may proactively:

- surface priorities;
- prepare recurring reports;
- follow approved workflows;
- identify overdue actions;
- detect business opportunities;
- suggest prospecting actions;
- execute pre-authorized recurring work.

---

# 7. Core Capability Domains

The platform must ultimately support the following domains.

---

## 7.1 Conversational Intelligence

EMEFA must support natural interaction.

Required direction:

- multi-turn conversation;
- contextual follow-up;
- interruption/resumption where modality permits;
- clarification when necessary;
- structured task extraction;
- conversation-to-action transition;
- concise progress communication;
- multimodal expansion.

The system must avoid pretending it performed actions when it only discussed them.

---

## 7.2 Personalized Onboarding

The onboarding engine must:

- ask adaptive questions;
- avoid redundant questions;
- allow skipping;
- distinguish facts from assumptions;
- capture structured information;
- allow later correction;
- resume incomplete onboarding;
- support progressive onboarding after first use.

The system should learn only what creates value.

---

## 7.3 Memory

EMEFA requires a durable memory architecture.

Memory categories should include, where appropriate:

### Profile Memory
Who the user is.

### Organization Memory
What the business is.

### Preference Memory
How the user likes work performed.

### Relationship Memory
People, companies, customers, partners.

### Procedural Memory
How recurring work is done.

### Episodic Memory
Relevant summaries of previous interactions/events.

### Active Work State
Current tasks, commitments, pending approvals.

### Knowledge Memory
Documents and connected organizational knowledge.

Memory must include provenance and user control where appropriate.

Do not implement memory as unlimited raw chat storage.

---

## 7.4 Administrative Assistant

EMEFA must progressively handle high-value administrative workflows.

Examples:

### Communication

- summarize inbox;
- identify important messages;
- draft replies;
- prepare follow-ups;
- track unanswered commitments.

### Calendar

- inspect schedule;
- propose meeting times;
- coordinate meetings;
- prepare agendas;
- generate meeting briefs.

### Meetings

- prepare context;
- summarize notes/transcripts;
- extract decisions;
- extract tasks;
- track follow-up.

### Documents

- create professional Word-style documents;
- format reports;
- prepare letters;
- generate quotations/proposals;
- update templates;
- apply brand standards.

### Spreadsheets

- create/update spreadsheets;
- analyze business data;
- produce tables;
- create charts;
- validate calculations.

### Presentations

- prepare presentations;
- apply brand templates;
- create structured slides;
- verify visual output where tooling permits.

OfficeCLI is a candidate provider for office-document capabilities.

The domain must remain provider-independent.

---

# 8. Priority Capability: Business Development Engine

Business development is a first-class module.

Its purpose is to help users continuously create qualified business opportunities.

---

## 8.1 Business Understanding

Before prospecting, EMEFA must understand:

- offer;
- positioning;
- target market;
- ideal customer profile;
- geography;
- deal size;
- qualification criteria;
- exclusions;
- communication style.

---

## 8.2 Prospect Discovery

EMEFA should search authorized sources for potential prospects.

It must record:

- source;
- reason for relevance;
- available business context;
- confidence/qualification.

No illegal scraping or prohibited data acquisition.

---

## 8.3 Prospect Research

For each candidate, EMEFA may:

- research company;
- identify needs/signals;
- identify likely relevance;
- summarize context;
- recommend approach.

---

## 8.4 Qualification

Prospects should be scored according to configurable criteria.

Do not rely solely on opaque LLM intuition.

Use explicit features where possible.

---

## 8.5 Outreach Preparation

EMEFA may prepare:

- email;
- messaging copy;
- LinkedIn-style outreach where permitted;
- call scripts;
- proposals.

Messages must be personalized and relevant.

Avoid mass generic spam.

---

## 8.6 Approval and Sending

External communication must follow configured permission rules.

Possible workflow:

```text
EMEFA discovers prospect
→ qualifies
→ drafts outreach
→ user approves
→ EMEFA sends through authorized channel
→ logs action
→ schedules follow-up
```

Later, trusted workflows may support scoped automation.

---

## 8.7 Follow-Up

EMEFA must help prevent opportunities from dying through forgotten follow-ups.

It should track:

- contact attempts;
- replies;
- next action;
- follow-up date;
- status;
- notes.

---

## 8.8 Pipeline

EMEFA should provide a simple pipeline view or integrate with existing CRM.

Users should be able to ask:

- Which prospects need follow-up?
- Which opportunities are hottest?
- Who has not replied?
- What should I do today?
- What opportunities appeared this week?

---

## 8.9 Continuous Business Development

With explicit authorization, EMEFA may run recurring workflows that:

- discover new prospects;
- monitor opportunity signals;
- prepare qualified prospect lists;
- recommend outreach;
- surface partnership opportunities.

Core experience:

> The user should feel that business development continues even while they focus elsewhere.

---

# 9. Skills Platform

EMEFA must support installable/extensible capabilities.

A skill may be:

- built-in;
- first-party;
- third-party;
- organization-specific;
- user-created.

Skill providers may include:

- native functions;
- APIs;
- MCP;
- CLI tools;
- SDKs;
- browser/computer-use;
- workflows;
- external agents.

---

## 9.1 Skill Registry

The system should maintain a registry containing:

- identity;
- version;
- description;
- capabilities;
- schemas;
- permissions;
- risk level;
- provider;
- health;
- availability;
- tenant eligibility.

---

## 9.2 Skill Discovery

EMEFA's orchestrator should select skills based on capability, not arbitrary tool names embedded everywhere.

---

## 9.3 Skill Installation

Future platform users should be able to add capabilities safely.

Installation must include:

- trust evaluation;
- requested permissions;
- configuration;
- credentials;
- test/health check;
- enable/disable;
- uninstall/revoke.

Never allow silent unrestricted tool installation.

---

# 10. MCP Integration

EMEFA should support MCP as an important integration standard.

Requirements:

- multiple MCP servers;
- tenant-specific configuration;
- credential isolation;
- tool discovery;
- schema validation;
- health checks;
- permission mapping;
- auditing;
- timeout/rate-limit controls.

Principle:

> MCP-first where it accelerates interoperability; never MCP-only.

---

# 11. External Agent Gateway

EMEFA should be capable of delegating specialist work to external agents such as Agent Zero or future systems.

The gateway must normalize:

- task request;
- context;
- permissions;
- timeout;
- status;
- output;
- errors;
- cancellation.

External agents must not receive unnecessary user secrets/context.

Their output is untrusted until validated.

They must not bypass EMEFA's permission engine.

---

# 12. Tool and Agent Orchestration

EMEFA requires an orchestration layer capable of:

- understanding task intent;
- deciding whether tools are required;
- decomposing complex tasks;
- selecting skills;
- requesting approvals;
- executing steps;
- tracking state;
- handling failures;
- verifying results;
- reporting status.

Avoid unnecessary multi-agent complexity.

Use the simplest execution strategy that reliably completes the task.

---

# 13. Permission and Autonomy Engine

Permissions must be first-class architecture.

The system should support policies based on:

- tenant;
- user;
- assistant;
- skill;
- action;
- data scope;
- risk;
- amount/threshold where applicable;
- destination;
- time/recurrence.

Autonomy levels:

```text
Suggest
Prepare
Execute after approval
Execute within policy
Proactive execution within policy
```

Permissions must be revocable.

---

# 14. Voice

Voice is an important interface.

Long-term capabilities:

- speech-to-text;
- low-latency conversation;
- interruption;
- natural text-to-speech;
- selectable voices;
- language detection;
- code-switching.

Voice is not a separate intelligence layer.

It uses the same EMEFA runtime and permissions.

---

# 15. African Language Strategy

EMEFA must create meaningful differentiation through African language and local-context support.

Potential initial language research should include languages relevant to Togo and regional expansion.

A language cannot be marked “supported” merely because a generic LLM recognizes some text.

Production support requires evaluation of:

- speech recognition;
- semantic understanding;
- business vocabulary;
- code-switching;
- speech synthesis;
- local names;
- task completion.

Language providers must be pluggable.

---

# 16. Multi-Tenant Platform

The end-state is not a single assistant.

The platform must support:

```text
Platform
  ├── Tenant / Organization A
  │     ├── Users
  │     ├── Assistant(s)
  │     ├── Memory
  │     ├── Skills
  │     ├── Credentials
  │     └── Audit
  │
  └── Tenant / Organization B
        └── Fully isolated resources
```

Tenant isolation is mandatory.

Never rely on prompts for isolation.

---

# 17. Assistant Studio

A future user should be able to configure their EMEFA.

Possible configuration:

- name;
- role;
- personality;
- voice;
- languages;
- goals;
- organization;
- memory;
- connected knowledge;
- skills;
- permissions;
- proactive workflows;
- communication style.

Configuration must be structured, not only a giant system prompt.

---

# 18. Knowledge Integration

EMEFA should be able to use authorized organizational knowledge.

Sources may include:

- uploaded files;
- cloud drives;
- policies;
- templates;
- CRM;
- project systems;
- websites;
- databases.

Requirements:

- access control;
- source attribution/provenance;
- freshness;
- deletion propagation where feasible;
- retrieval quality;
- tenant isolation.

---

# 19. Proactivity

Proactivity is a core long-term capability.

EMEFA may proactively identify:

- overdue commitments;
- unanswered important emails;
- upcoming meetings requiring preparation;
- prospects requiring follow-up;
- recurring administrative tasks;
- business opportunities;
- anomalies in connected business data.

Proactivity must be:

- permissioned;
- configurable;
- non-annoying;
- explainable;
- cancellable.

Do not create autonomous behavior without clear boundaries.

---

# 20. Notifications

EMEFA should eventually notify users through authorized channels.

Notifications must support:

- urgency;
- batching;
- quiet hours;
- preferences;
- deduplication.

Avoid notification spam.

---

# 21. Auditability

Every consequential action should create an audit record.

Record, where appropriate:

- actor;
- assistant;
- tenant;
- intent;
- skill/tool;
- approval;
- action;
- result;
- timestamps;
- correlation ID.

Sensitive content should be minimized/redacted.

---

# 22. Observability

The system must expose operational visibility into:

- latency;
- failures;
- tool health;
- workflow state;
- model usage;
- cost;
- retries;
- approval delays;
- task success.

Agent systems cannot be operated safely as black boxes.

---

# 23. Evaluation System

EMEFA requires continuous evaluation.

Core evaluation dimensions:

- task completion;
- correctness;
- hallucination;
- tool selection;
- permission compliance;
- memory retrieval;
- memory writes;
- prompt injection resistance;
- recovery;
- language performance;
- cost;
- latency.

Regression evaluations should run when important prompts/models/orchestration change.

---

# 24. Security Requirements

Production design must include:

- authentication;
- authorization;
- tenant isolation;
- least privilege;
- secret vaulting;
- encryption;
- audit logs;
- secure APIs;
- secure file processing;
- prompt injection defenses;
- tool sandboxing where needed;
- controlled network access;
- dependency scanning;
- abuse controls;
- backup/recovery;
- incident readiness.

Never expose raw credentials to untrusted tools or model context unnecessarily.

---

# 25. Privacy and User Ownership

Users should retain meaningful control over their information.

Design for:

- memory inspection;
- correction;
- deletion;
- export;
- credential revocation;
- assistant deletion;
- organization deletion subject to legal requirements.

Retention must be configurable where necessary.

Do not create artificial lock-in by trapping user data.

Retention should come from value.

---

# 26. Model Architecture

EMEFA must support multiple AI providers/models.

Potential model roles:

- conversational reasoning;
- fast classification;
- extraction;
- planning;
- embeddings;
- vision;
- speech;
- specialist tasks.

Use routing.

Do not send every task to the most expensive model.

Provider-specific APIs should remain behind adapters where practical.

---

# 27. Workflow Engine

Complex and recurring tasks require durable execution.

The workflow system should support:

- state persistence;
- retries;
- timeouts;
- waiting for approval;
- waiting for external events;
- scheduling;
- cancellation;
- resumability;
- audit.

Examples:

```text
Prospecting campaign
Invoice follow-up
Meeting preparation
Weekly business report
Lead follow-up
Document approval
```

---

# 28. Office and Document Engine

EMEFA should produce professional business artifacts.

Candidate capabilities:

- DOCX;
- XLSX;
- PPTX;
- PDF;
- templates;
- brand standards;
- rendering/visual validation.

OfficeCLI should be evaluated as one implementation provider.

Required abstraction:

```text
Document Capability Interface
        ↓
Provider Adapter
        ↓
OfficeCLI / Other Engine
```

---

# 29. Computer and Browser Use

Some tasks may require interaction with systems lacking APIs.

Computer/browser use may be supported, but must be treated as higher risk.

Requirements:

- sandboxing/isolation;
- domain allowlists where appropriate;
- credential controls;
- action previews/approvals;
- screenshots/evidence;
- timeout;
- audit;
- injection defenses.

Prefer APIs over brittle UI automation when reliable APIs exist.

---

# 30. Product Surfaces

Potential surfaces include:

- web application;
- mobile application;
- desktop application;
- voice interface;
- messaging channels;
- APIs.

Do not build all surfaces simultaneously.

Build shared platform capabilities first.

---

# 31. User Zero Strategy

The first serious deployment should be used by a real design partner/user zero.

Purpose:

- identify daily high-value workflows;
- measure time saved;
- discover missing skills;
- validate memory;
- validate trust;
- identify failure modes.

Every repeated statement:

> “I wish EMEFA could do this”

should be captured as product research, then prioritized by value and feasibility.

Do not automatically implement every request.

---

# 32. MVP Definition

The MVP must prove **real work**, not total vision.

A credible MVP should demonstrate an end-to-end loop:

1. User creates/configures EMEFA.
2. EMEFA conducts onboarding.
3. EMEFA stores structured business context.
4. User connects at least a small set of useful tools.
5. EMEFA performs administrative tasks.
6. EMEFA produces professional documents.
7. EMEFA supports a basic business-development workflow.
8. Permission/approval controls work.
9. Actions are audited.
10. Memory improves subsequent interactions.
11. Failures are represented honestly.

The MVP should be extensible enough to add skills without rewriting the core.

---

# 33. Priority MVP Demonstration Scenarios

The MVP should target compelling scenarios.

## Scenario A — Executive Morning Brief

User asks:

> “EMEFA, what needs my attention today?”

EMEFA may combine authorized:

- calendar;
- tasks;
- important communications;
- pending commitments;
- prospect follow-ups.

It returns a prioritized briefing.

---

## Scenario B — Professional Document

User asks:

> “Prepare a proposal for this client using our company style.”

EMEFA:

- retrieves business/brand context;
- retrieves client context;
- drafts content;
- generates the document;
- formats it;
- verifies output;
- provides result.

---

## Scenario C — Prospecting

User asks:

> “Find companies matching our target customer profile and prepare the best prospects for review.”

EMEFA:

- retrieves ICP;
- searches authorized sources;
- researches;
- qualifies;
- explains relevance;
- prepares outreach drafts;
- waits for required approval.

---

## Scenario D — Meeting Preparation

User asks:

> “Prepare me for my meeting with Company X.”

EMEFA:

- retrieves calendar;
- retrieves relevant correspondence/documents;
- summarizes relationship/history;
- identifies open items;
- creates briefing.

---

## Scenario E — Learning Preference

User corrects:

> “Never make my proposals longer than five pages unless I ask.”

Future relevant proposals follow this preference, subject to user control over stored memory.

---

# 34. Architecture Quality Bar

The implementation must aim for professional software-engineering standards.

Required characteristics:

- modular;
- typed;
- testable;
- observable;
- secure;
- documented;
- deployable;
- maintainable;
- extensible.

Avoid both extremes:

- prototype spaghetti;
- over-engineered distributed architecture before product validation.

---

# 35. Development Strategy

Claude must build incrementally.

Recommended sequence:

### Milestone 0 — Current-State Audit and Specification Reconciliation
Audit the existing Hermes-built repository before major code changes.

Produce `docs/CURRENT_STATE_ASSESSMENT.md` covering:
- repository/component map;
- current architecture and data flows;
- existing UI/3D experience;
- current voice pipeline;
- memory/tool/security implementation;
- tests and deployment state;
- dependencies and provider lock-in;
- what to keep, refactor, migrate, or replace;
- migration risks and rollback requirements.

Then reconcile all foundational specifications against the actual implementation.

### Milestone 1 — Engineering Foundation
Repository, CI, environments, architecture skeleton, observability baseline.

### Milestone 2 — Identity & Tenancy
Users, organizations, assistants, authorization.

### Milestone 3 — Onboarding & Profiles
Conversational discovery and structured context.

### Milestone 4 — Memory & Knowledge
Controlled memory and retrieval.

### Milestone 5 — Skills/Tool Gateway
Capability registry and execution contracts.

### Milestone 6 — Orchestration & Permissions
Task lifecycle, approvals, execution state.

### Milestone 7 — Administrative Vertical Slice
Real administrative workflows.

### Milestone 8 — Office Documents
Professional artifact generation.

### Milestone 9 — Business Development
Prospecting and follow-up vertical slice.

### Milestone 10 — Proactivity
Scheduled/conditional workflows.

### Milestone 11 — Voice/Language
Voice foundation and evaluated language expansion.

### Milestone 12 — Platformization
Assistant creation at scale, ecosystem, billing/enterprise concerns as validated.

Each milestone requires acceptance criteria before implementation.

---

# 36. Non-Goals for Early Versions

Do not attempt immediately:

- fully autonomous company management;
- unrestricted financial transactions;
- unrestricted computer control;
- every African language;
- every SaaS integration;
- a giant skill marketplace;
- dozens of autonomous sub-agents;
- every communication channel;
- full enterprise feature parity;
- perfect AGI-like behavior.

Build a strong foundation and high-value workflows first.

---

# 37. Anti-Patterns

The project has failed architecturally if:

- EMEFA is only a prompt;
- all logic lives inside one giant agent loop;
- one model provider is impossible to replace;
- external agents bypass permissions;
- tools have unrestricted access;
- tenant data can leak;
- memory is only raw conversation history;
- actions cannot be audited;
- failures are reported as success;
- adding a skill requires rewriting core orchestration;
- business-development becomes spam automation;
- language support is claimed without evaluation;
- every feature requires Claude/Hermes to manually intervene in production.

---

# 38. Definition of Done — Platform Foundation

The foundation is considered complete only when:

- product specifications are coherent;
- architecture is documented;
- key ADRs exist;
- threat model exists;
- tenancy model exists;
- permission model exists;
- skill contract exists;
- execution lifecycle exists;
- memory model exists;
- observability strategy exists;
- test/evaluation strategy exists;
- deployment strategy exists.

---

# 39. Definition of Done — MVP

The MVP is done only when:

### Product

- A user can create/configure an assistant.
- Conversational onboarding creates structured context.
- EMEFA can perform at least several real administrative workflows.
- EMEFA can create professional business artifacts.
- A business-development workflow works end-to-end.
- Users can connect approved tools.
- Users can control permissions.
- Memory demonstrably improves later work.

### Engineering

- Core tests pass.
- Critical integration tests pass.
- End-to-end scenarios pass.
- AI evaluations meet defined thresholds.
- CI/CD exists.
- Environments are reproducible.
- Database migrations are managed.
- Secrets are externalized.

### Security

- Authentication and authorization are enforced.
- Tenant isolation is tested.
- Secrets are protected.
- Tool permissions are enforced server-side.
- Prompt-injection defenses exist for relevant flows.
- High-risk actions require appropriate control.
- Audit logs exist.

### Reliability

- Tool failures are handled.
- Retries are bounded.
- Long-running work is durable where necessary.
- Users can see failures.
- No action is falsely reported as completed.

### Operations

- Structured logging exists.
- Error monitoring exists.
- Core metrics exist.
- Model/tool usage can be measured.
- Cost can be monitored.

### Documentation

- setup documentation works;
- architecture reflects implementation;
- API/tool contracts are documented;
- operational runbooks exist for critical flows.

---

# 40. Definition of Done — Production Candidate

Before calling EMEFA production-ready:

- security review completed;
- privacy review completed;
- backup/restore tested;
- disaster/recovery expectations defined;
- load/performance tested for expected scale;
- observability dashboards exist;
- alerting exists;
- incident response process exists;
- dependency/license review completed;
- user data export/deletion flows tested;
- billing/entitlement controls tested if enabled;
- rollback strategy tested;
- key AI regression suites established;
- documented known limitations exist.

---

# 41. Success Metrics

The platform should eventually measure:

## User Value

- hours saved;
- tasks completed;
- administrative workload reduced;
- response/follow-up time reduced;
- documents produced;
- qualified opportunities generated;
- meetings prepared;
- recurring workflows automated.

## Trust

- approval rate;
- correction rate;
- rollback/error rate;
- task success;
- verified completion;
- user retention.

## Business Development

- qualified prospects;
- outreach approved;
- response rate;
- meetings generated;
- opportunities created;
- conversions attributable/assisted.

Do not optimize vanity metrics such as raw messages generated.

---

# 42. Competitive Moat

EMEFA's defensibility should come from the combination of:

- accumulated user-specific context;
- business-specific procedural memory;
- trusted execution;
- extensible skills;
- workflow history;
- local market understanding;
- African language/voice capabilities;
- integrations;
- high-quality business-development workflows;
- ecosystem effects.

Do not depend on artificial data lock-in.

---

# 43. Product Philosophy

The strongest EMEFA should feel less like software that the user operates and more like a trusted collaborator the user delegates to.

But trust must be earned through:

- competence;
- transparency;
- predictability;
- control;
- privacy;
- measurable value.

Personality and voice are important.

Execution quality is more important.

---

# 44. Final Instruction to Claude

Do not attempt to satisfy this Master Goal by generating a huge amount of code in one pass.

Your responsibility is to turn this goal into a coherent, production-grade system through disciplined engineering.

For every major milestone:

1. read governing specifications;
2. inspect current state;
3. identify unresolved decisions;
4. propose architecture/implementation plan;
5. obtain approval where required;
6. implement incrementally;
7. test;
8. evaluate;
9. verify;
10. document;
11. report honestly.

Never reduce the vision to a superficial chatbot because it is easier.

Never over-engineer speculative infrastructure at the expense of user value.

Build the smallest architecture that can correctly support the validated next stage while preserving the long-term boundaries defined here.

---


# 44A. Voice Migration Definition of Done

A migration from the existing ElevenLabs Agents integration to LiveKit or another realtime architecture is complete only when:

- conversational latency is measured and acceptable;
- interruption remains reliable;
- progressive transcription remains reliable;
- mobile and desktop browser behavior is verified;
- connection recovery is tested;
- STT/TTS quality is benchmarked;
- cost per active minute is documented;
- African-accent/local-language tests are included;
- observability exists;
- security/session handling is reviewed;
- rollback to the previous implementation is possible during migration.

Cost reduction alone is not sufficient if the user experience becomes materially worse.

# 45. Ultimate End State

The long-term target is a platform where a user can say:

> “This is my company. This is how we work. These are the tools you may use. These are the things you may do without asking me. Help me run this business.”

And EMEFA can:

- understand;
- remember;
- plan;
- act;
- coordinate;
- verify;
- learn;
- proactively assist;

while remaining secure, controllable, transparent, extensible, and deeply personalized.

That is the Master Goal.

**Claude builds the platform.**

**EMEFA becomes the assistant.**

**The user remains in control.**
