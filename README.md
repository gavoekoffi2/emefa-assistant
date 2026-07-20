# EMEFA

> **AI Executive Assistant Platform — African-rooted, globally extensible**

EMEFA is an evolving platform for creating deeply personalized AI executive assistants for entrepreneurs, executives, SMEs, and organizations.

This repository already contains a working foundation created during an earlier engineering phase. It is **not a blank-slate project**. All future engineering work must continue, harden, extend, and elevate the existing implementation rather than restart it without evidence-based justification.

The product vision is simple:

> **Create an AI assistant that understands your business and actually works with you.**

EMEFA is not intended to be a chatbot with a voice interface. It is being built as an **agentic work platform** capable of understanding context, remembering relevant information, using authorized tools, executing real tasks, verifying outcomes, and becoming progressively more useful over time.

---

## 1. Current Repository Baseline

At the time this specification was updated, the repository contains an existing EMEFA implementation whose documented baseline includes:

- `web/` — React/TypeScript, mobile-first, installable PWA;
- `backend/` — FastAPI backend with private server-side APIs;
- real-time voice conversation;
- interruptible spoken interaction;
- progressive transcription;
- server-side provider credentials;
- bounded agent orchestration;
- action-risk policies and confirmation flows;
- memory/audit foundations;
- an allowlisted tool model;
- deployment documentation;
- an experimental/previous Android area that is not the primary shipped product.

**The repository itself is the source of truth for actual implementation state.**

Before major engineering work, Claude must inspect the current code and produce/update:

`docs/CURRENT_STATE_ASSESSMENT.md`

That assessment must identify what exists, what works, what is incomplete, what should be preserved, what should be refactored, and what—if anything—requires migration or replacement.

---

## 2. Brownfield Continuation Rule

### Do not restart EMEFA from zero.

The existing implementation represents valuable engineering work.

Any coding agent working on EMEFA must:

1. inspect existing code before changing architecture;
2. preserve working product value;
3. maintain backward compatibility where appropriate;
4. prefer incremental migration over destructive rewrites;
5. justify major replacements with evidence;
6. create rollback paths for risky migrations;
7. keep documentation aligned with reality.

A rewrite is justified only when supported by a clear reason such as:

- security vulnerability;
- severe architectural dead-end;
- unacceptable cost;
- unacceptable reliability;
- maintainability failure;
- inability to meet validated product requirements;
- harmful provider lock-in;
- material performance limitations.

“Another technology looks better” is not sufficient justification.

---

## 3. What EMEFA Must Become

The target is a platform where a user can create an assistant that progressively:

- understands who they are;
- understands their company and business model;
- understands their products, services, customers, team, and goals;
- learns their working preferences;
- maintains useful and controllable memory;
- communicates naturally through text and voice;
- uses authorized tools and skills;
- performs administrative work;
- supports continuous business development;
- coordinates external specialist agents when useful;
- executes recurring workflows;
- acts proactively within explicit permissions;
- verifies work before claiming completion.

The target interaction model is:

```text
User Intent
    ↓
Context + Memory
    ↓
Understand Required Outcome
    ↓
Plan if Needed
    ↓
Policy / Permission Check
    ↓
Select Skill / Tool / Agent
    ↓
Execute
    ↓
Verify
    ↓
Report
    ↓
Audit + Relevant Memory Update
```

The user interacts with **EMEFA**.

They should not need to care whether a task internally used an API, MCP server, CLI, external agent, browser automation, office engine, or AI model.

---

## 4. JARVIS-Class Experience — EMEFA Identity

EMEFA should deliver the sense of presence associated with advanced fictional assistants such as JARVIS:

- immediate responsiveness;
- natural spoken conversation;
- interruption/barge-in;
- fluid visual feedback;
- contextual awareness;
- subtle personality and humor;
- proactive assistance;
- immersive spatial/3D interaction where useful;
- clear awareness of what the assistant is doing.

The goal is:

> **JARVIS-class presence and fluidity — not a JARVIS clone.**

EMEFA must have its own identity.

Do not copy copyrighted voice identities, protected audiovisual assets, dialogue, logos, or proprietary visual designs.

The interface should evolve toward an immersive, futuristic, high-quality assistant experience while preserving:

- usability;
- accessibility;
- mobile performance;
- low latency;
- clarity;
- business usefulness.

3D and animation must communicate state and intelligence, not become decorative “bling-bling.”

---

## 5. Core Product Pillars

### 5.1 Deep Personalization

EMEFA must first understand the person it works with.

Initial onboarding should be conversational and adaptive.

EMEFA should learn, where relevant:

- identity and role;
- company;
- industry;
- products/services;
- business model;
- target customers;
- markets;
- team;
- recurring workflows;
- objectives;
- constraints;
- preferred communication style;
- tools already used;
- document/brand standards;
- languages;
- autonomy preferences.

This information becomes structured, inspectable context.

Personalization must continue over time through:

- explicit instructions;
- corrections;
- approvals/rejections;
- recurring behavior;
- new business knowledge;
- installed skills.

Retention must come from accumulated usefulness, not artificial lock-in.

---

### 5.2 Executive and Administrative Assistance

EMEFA must progressively perform high-value work expected from a strong executive assistant.

Examples:

- inbox triage;
- email drafting and follow-up;
- calendar coordination;
- meeting preparation;
- meeting summaries;
- action-item tracking;
- task follow-up;
- reports;
- letters;
- proposals;
- quotations;
- invoices where connected systems permit;
- professional documents;
- spreadsheets and analysis;
- presentations;
- recurring administrative workflows.

Office/document execution should be abstracted behind an internal capability interface.

**OfficeCLI** is a candidate provider for Word, Excel, and PowerPoint operations and should be evaluated/integrated through an adapter rather than hard-wired into the domain.

---

### 5.3 Business Development and Continuous Prospecting

Customer acquisition is a critical pain point for entrepreneurs and SMEs.

Business development is therefore a **priority product pillar**.

EMEFA should progressively:

1. understand the user's offer;
2. model the ideal customer profile;
3. discover prospects from authorized sources;
4. research prospects;
5. qualify them;
6. explain why they are relevant;
7. prepare personalized outreach;
8. request approval when required;
9. send through authorized channels;
10. track responses;
11. manage follow-ups;
12. maintain pipeline context;
13. prepare commercial proposals;
14. surface next-best business actions.

Core promise:

> **While you run your business, EMEFA helps create your next opportunities.**

EMEFA must never become an uncontrolled spam engine.

---

## 6. Voice Architecture

The existing implementation already provides real-time voice capabilities.

That user experience is valuable and must not be casually discarded.

However, EMEFA must evolve toward a **provider-flexible voice architecture**.

Target conceptual pipeline:

```text
Microphone
    ↓
Realtime Transport / Session Layer
    ↓
VAD / Turn Detection
    ↓
Speech-to-Text
    ↓
EMEFA Runtime
(Memory + Orchestration + Skills)
    ↓
Text-to-Speech
    ↓
Realtime Audio Stream
    ↓
User
```

### Strategic direction

A framework such as **LiveKit** should be evaluated as a realtime transport/agent-session foundation because it can allow EMEFA to decouple:

- realtime media;
- STT;
- LLM/runtime;
- TTS.

The architecture should support provider adapters such as:

```text
Voice Runtime
├── Realtime Transport
│   └── LiveKit or equivalent
├── STT Providers
│   ├── cloud provider
│   ├── open/self-hosted model
│   └── future African-language provider
└── TTS Providers
    ├── economical default
    ├── open/self-hosted option
    ├── ElevenLabs premium option
    └── future African-language provider
```

### ElevenLabs policy

Do **not** remove the existing ElevenLabs integration immediately.

ElevenLabs may remain:

- the current working implementation during migration;
- a premium voice provider;
- a fallback;
- an option for users requiring higher voice quality.

Before replacing any working voice path:

1. benchmark current performance;
2. implement abstraction/adapters;
3. implement alternative;
4. test side-by-side;
5. compare cost, quality, latency, reliability, and language performance;
6. migrate gradually;
7. preserve rollback.

---

## 7. Voice Quality and Cost Benchmark

Voice technology decisions must be evidence-based.

Measure:

- end-to-end latency;
- time-to-first-audio;
- interruption/barge-in quality;
- STT accuracy;
- African accent performance;
- local-language performance;
- TTS naturalness;
- prosody/emotion;
- mobile stability;
- reconnection;
- concurrent-session behavior;
- cost per active voice minute;
- infrastructure cost;
- operational complexity;
- privacy;
- vendor lock-in.

**Free is not automatically cheaper.**

Self-hosted systems may require GPUs, infrastructure, scaling, monitoring, and maintenance.

Evaluate total cost of ownership.

---

## 8. African-Rooted Differentiation

EMEFA is intended to be designed from African realities outward while remaining globally extensible.

Differentiation should eventually include:

- African languages;
- African accents;
- natural code-switching;
- culturally appropriate interaction;
- local business workflows;
- locally relevant channels and integrations;
- mobile-first experiences;
- bandwidth-conscious operation;
- regional business context.

Potential early language research may include languages relevant to Togo and neighboring markets, including Ewe and Kabiye, subject to technical validation.

A language is not “supported” merely because an LLM recognizes a few phrases.

Production support requires evaluation of:

- speech recognition;
- semantic understanding;
- business vocabulary;
- code-switching;
- local names/entities;
- TTS quality;
- end-to-end task completion.

> **Local language is a strategic accelerator. Real work execution remains the core value.**

---

## 9. Skills and Tool Ecosystem

EMEFA must gain capabilities through a modular Skills architecture.

A Skill may be powered by:

- native functions;
- APIs;
- MCP servers;
- CLIs;
- SDKs;
- workflow engines;
- browser/computer-use;
- external agents.

Examples:

- OfficeCLI;
- email;
- calendar;
- contacts;
- cloud files;
- CRM;
- business messaging;
- research;
- browser automation;
- accounting/business software;
- analytics;
- code/development systems.

Each production skill should expose, where appropriate:

- identity;
- version;
- description;
- input/output schema;
- permissions;
- risk classification;
- provider;
- health;
- timeout/retry policy;
- audit hooks;
- verification strategy.

---

## 10. MCP Strategy

EMEFA should be:

> **MCP-first where useful, but never MCP-only.**

Support should eventually include:

- multiple MCP servers;
- tenant/user-specific configuration;
- credential isolation;
- tool discovery;
- schema validation;
- permission mapping;
- health checks;
- auditing;
- rate/timeout controls.

MCP output must be treated as untrusted external data until validated.

---

## 11. External Agent Gateway

Specialized external systems such as Agent Zero may be integrated when they provide useful capabilities.

They must remain specialist workers.

```text
User
 ↓
EMEFA
 ↓
Orchestrator
 ↓
Agent / Tool Gateway
 ↓
External Specialist
 ↓
Verification
 ↓
EMEFA
 ↓
User
```

External agents:

- must not become EMEFA's identity;
- must not bypass EMEFA permissions;
- should receive only necessary context;
- must have bounded execution;
- must return inspectable results.

Claude and Hermes are development/engineering agents, not automatic runtime dependencies.

---

## 12. Memory

Memory must make EMEFA more useful over time without becoming uncontrolled surveillance or raw chat storage.

Potential memory domains:

- user profile;
- organization profile;
- preferences;
- relationships;
- business entities;
- procedures;
- episodic summaries;
- active commitments;
- organizational knowledge.

Memory should be:

- tenant-isolated;
- provenance-aware;
- permission-aware;
- inspectable;
- correctable;
- exportable;
- deletable.

---

## 13. Autonomy and Permissions

EMEFA must support graduated autonomy:

1. **Suggest**
2. **Prepare**
3. **Execute after approval**
4. **Execute within scoped policy**
5. **Proactive execution within scoped policy**

Risk-sensitive actions require stronger safeguards.

Examples:

- read-only retrieval → potentially automatic;
- draft creation → generally low/moderate risk;
- external communication → approval according to policy;
- destructive actions → strong confirmation;
- financial/legal/security actions → strict controls.

Never infer unlimited authorization from vague user intent.

---

## 14. Multi-Tenant Platform Vision

EMEFA must not remain a hard-coded assistant for one user.

Long-term structure:

```text
EMEFA Platform
├── Organization / Tenant A
│   ├── Users
│   ├── Assistant(s)
│   ├── Memory
│   ├── Knowledge
│   ├── Skills
│   ├── Credentials
│   ├── Workflows
│   └── Audit
└── Organization / Tenant B
    └── Fully isolated resources
```

Tenant isolation must be enforced technically, not through prompts.

---

## 15. Product Value Gate

EMEFA must not become a collection of impressive demos.

Before prioritizing a feature, ask:

1. What painful problem does it solve?
2. How frequently does that problem occur?
3. Does it save meaningful time, money, cognitive load, or lost opportunity?
4. Can the outcome be measured?
5. Can EMEFA perform it reliably enough to earn trust?

No “AI magic” feature should displace higher-value operational workflows merely because it looks impressive.

---

## 16. Engineering Principles

All contributors and coding agents must follow:

- security by design;
- privacy by design;
- tenant isolation;
- least privilege;
- human control for consequential actions;
- auditability;
- observability;
- provider abstraction where valuable;
- typed/versioned contracts;
- idempotency where relevant;
- graceful failure;
- explicit state;
- evaluation-driven AI development;
- no fake completion;
- no hard-coded secrets;
- no uncontrolled tool execution;
- no unnecessary vendor lock-in;
- no premature microservice explosion.

Prefer clean modular boundaries before distributed complexity.

---

## 17. Repository Documentation Target

```text
/
├── README.md
├── CLAUDE.md
├── docs/
│   ├── CURRENT_STATE_ASSESSMENT.md
│   ├── MASTER_GOAL.md
│   ├── PRODUCT_VISION.md
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DOMAIN_MODEL.md
│   ├── DATA_ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── PRIVACY.md
│   ├── MEMORY_SYSTEM.md
│   ├── AGENT_ORCHESTRATION.md
│   ├── SKILLS_AND_TOOLS.md
│   ├── MCP_INTEGRATION.md
│   ├── EXTERNAL_AGENT_GATEWAY.md
│   ├── PERMISSIONS_AND_AUTONOMY.md
│   ├── VOICE_ARCHITECTURE.md
│   ├── VOICE_AND_LANGUAGES.md
│   ├── BUSINESS_DEVELOPMENT.md
│   ├── ADMIN_ASSISTANT.md
│   ├── API_CONTRACTS.md
│   ├── OBSERVABILITY.md
│   ├── EVALUATION_STRATEGY.md
│   ├── TEST_STRATEGY.md
│   ├── DEPLOYMENT.md
│   ├── ROADMAP.md
│   └── adr/
│       └── README.md
└── tasks/
    └── ...
```

This structure may evolve through approved architectural decisions.

---

## 18. Mandatory First Task for Claude

Before major feature implementation, Claude must:

1. read `README.md`;
2. read `CLAUDE.md`;
3. read `docs/MASTER_GOAL.md`;
4. inspect the complete existing repository;
5. inspect current documentation;
6. run available tests/build checks where feasible;
7. map existing architecture;
8. produce `docs/CURRENT_STATE_ASSESSMENT.md`.

The assessment must include:

- repository map;
- frontend architecture;
- backend architecture;
- current UI/3D implementation;
- current voice pipeline;
- data/storage;
- memory;
- orchestration;
- tools;
- security;
- external services;
- tests;
- deployment;
- technical debt;
- provider lock-in;
- what to keep;
- what to refactor;
- what to migrate;
- what to replace;
- risks;
- recommended next milestone.

Claude must not perform a major rewrite before this assessment.

---

## 19. Initial Development Strategy

### Phase 0 — Audit Existing Product

Understand the Hermes-built implementation.

### Phase 1 — Reconcile Architecture

Align existing implementation with target specifications.

### Phase 2 — Harden Foundations

Identity, tenancy, permissions, security, audit, observability.

### Phase 3 — Deep Personalization

Conversational onboarding and structured business context.

### Phase 4 — Memory

Durable, controlled personalization.

### Phase 5 — Skills Gateway

MCP/API/CLI/external-agent capability architecture.

### Phase 6 — Administrative Assistant

High-value real workflows.

### Phase 7 — Office Capabilities

OfficeCLI or equivalent through adapters.

### Phase 8 — Business Development

Continuous prospecting and opportunity workflows.

### Phase 9 — Proactivity

Recurring/conditional work.

### Phase 10 — Voice Optimization

Provider-flexible realtime architecture and cost optimization.

### Phase 11 — African Languages

Evaluated language and voice expansion.

### Phase 12 — Platformization

Generalized assistant creation for many users/organizations.

---

## 20. Core Demonstration Experiences

### Executive Morning Brief

> “EMEFA, qu'est-ce qui demande mon attention aujourd'hui ?”

EMEFA combines authorized calendar, tasks, communications, commitments, and business-development follow-ups.

### Professional Document

> “Prépare une proposition pour ce client avec notre style.”

EMEFA retrieves context, creates, formats, verifies, and returns a professional artifact.

### Continuous Prospecting

> “Trouve-moi de nouvelles entreprises qui correspondent à notre cible.”

EMEFA discovers, researches, qualifies, explains relevance, and prepares next actions.

### Meeting Preparation

> “Prépare-moi pour ma réunion avec cette entreprise.”

EMEFA retrieves relevant context and produces a concise briefing.

### Learned Preference

> “Mes propositions ne doivent pas dépasser cinq pages sauf si je te le demande.”

Future relevant work reflects the preference, with memory remaining user-controllable.

---

## 21. Definition of Real Progress

A feature is not complete because a model demonstrated it once.

Production capability requires, where applicable:

- clear user value;
- defined contracts;
- permission boundaries;
- error handling;
- retries/idempotency;
- verification;
- observability;
- audit;
- tests;
- AI evaluations;
- security review;
- documentation;
- acceptable latency;
- known cost.

Distinguish:

```text
Prototype
   ↓
Alpha Capability
   ↓
Validated Capability
   ↓
Production-Ready Capability
```

Never present one as another.

---

## 22. Core Standard

Every product and engineering decision should preserve this principle:

> **EMEFA is not valuable because it sounds intelligent. EMEFA is valuable because it understands the user, performs useful work reliably, creates opportunities, and compounds its usefulness over time.**

And every coding agent must preserve this distinction:

> **Claude/Hermes build and maintain EMEFA. EMEFA performs the work for its users.**

---

## 23. Next Foundational Documents

After this updated README:

1. `CLAUDE.md` — permanent engineering constitution, updated for brownfield continuation.
2. `docs/MASTER_GOAL.md` — authoritative end-state objective.
3. `docs/CURRENT_STATE_ASSESSMENT.md` — generated from actual repository inspection.
4. `docs/PRODUCT_VISION.md` — positioning, users, value, differentiation.
5. `docs/PRD.md` — detailed requirements and acceptance criteria.
6. `docs/ARCHITECTURE.md` — reconciled target architecture and migration path.
7. `docs/VOICE_ARCHITECTURE.md` — LiveKit/provider-flexible realtime strategy and benchmarks.

**Do not begin broad rewrites before the current-state audit and architecture reconciliation are complete.**

---

## 24. Development Quickstart (verified)

```bash
# Backend (Python >= 3.11)
cd backend
pip install -e ".[test]"
cp ../.env.example ../.env        # then edit values; EMEFA_COOKIE_SECURE=false for local HTTP
uvicorn emefa.main:app --port 8765
python -m pytest                  # test suite

# Frontend (Node 22)
cd web
npm ci
npm run dev                       # proxies /v1 and /health to 127.0.0.1:8765
npm run lint && npm test && npm run build
```

Without API keys the app runs fully: voice returns 503 `realtime_not_configured` and the text
agent answers that the language engine is not configured. Production deployment: see
`docs/DEPLOIEMENT.md`. Current state and next steps: `docs/IMPLEMENTATION_STATUS.md`.
