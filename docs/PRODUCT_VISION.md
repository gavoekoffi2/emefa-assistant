# EMEFA — PRODUCT_VISION.md

> **Document type:** Product vision and strategic positioning  
> **Project:** EMEFA  
> **Status:** Foundational product specification  
> **Starting point:** Existing EMEFA implementation initiated by Hermes; future engineering must continue and elevate the existing product.  
> **Primary audience:** Product owner, Claude, Hermes, engineering agents, designers, partners, and future team members.

---

# 1. Vision

EMEFA is a deeply personalized AI executive assistant platform designed to help entrepreneurs, executives, SMEs, and organizations **get real work done**.

The long-term vision is:

> **Every entrepreneur should be able to have an intelligent assistant that understands their business, remembers how they work, communicates naturally, uses the tools they authorize, performs useful work, helps create business opportunities, and becomes more valuable over time.**

EMEFA begins with the realities of African entrepreneurs and businesses, while being designed as a globally extensible platform.

---

# 2. The Problem

Entrepreneurs and SME leaders often operate with too much responsibility concentrated in too few people.

A founder may simultaneously need to:

- find new customers;
- respond to messages;
- prepare quotations and proposals;
- follow up with prospects;
- manage appointments;
- prepare meetings;
- create documents;
- coordinate employees;
- track commitments;
- research opportunities;
- monitor operations;
- remember dozens of small but important details.

Many of these tasks are individually simple.

The problem is their accumulation.

The result is:

- lost time;
- missed follow-ups;
- delayed decisions;
- inconsistent execution;
- lost commercial opportunities;
- administrative overload;
- cognitive overload.

Hiring an excellent full-time executive assistant or multiple specialists is not always economically possible, especially for smaller organizations.

Existing AI chatbots can answer questions and generate content, but often stop at:

> “Here is what you could do.”

EMEFA's ambition is to move toward:

> **“I understood what needs to be done, I used the authorized resources, I performed the work, I verified the result, and here is what needs your attention.”**

---

# 3. Primary Target Market

The initial priority market is:

## Entrepreneurs and SME/SMI leaders

Especially people who:

- personally handle many operational responsibilities;
- lack a full administrative support team;
- need more customers;
- lose time on repetitive administrative work;
- use several disconnected digital tools;
- need faster execution without immediately increasing headcount.

Initial geographic relevance is strongly African, beginning with realities familiar to Togo and West Africa.

The architecture and product must nevertheless remain globally extensible.

---

# 4. Initial User Profiles

## 4.1 Entrepreneur / Founder

Needs:

- customers;
- follow-up;
- organization;
- documents;
- research;
- reminders;
- administrative support.

Core desired outcome:

> “Help me run the business without everything depending on my memory and my personal time.”

## 4.2 SME Director

Needs:

- executive briefing;
- meeting preparation;
- reporting;
- document production;
- coordination;
- decision support;
- delegation.

Core desired outcome:

> “Give me leverage without forcing me to manage another complicated software stack.”

## 4.3 Commercially Focused Business Owner

Needs:

- prospect discovery;
- qualification;
- personalized outreach;
- follow-up;
- pipeline visibility;
- proposals.

Core desired outcome:

> “Help me continuously create qualified business opportunities.”

## 4.4 Professional / Consultant

Needs:

- proposals;
- client follow-up;
- scheduling;
- research;
- reports;
- presentations;
- knowledge organization.

Core desired outcome:

> “Act like an assistant who already understands my practice.”

---

# 5. Core Product Promise

EMEFA should eventually deliver four forms of leverage.

## Understand

EMEFA understands:

- the user;
- their organization;
- their business;
- their customers;
- their goals;
- their preferences;
- their workflows.

## Remember

EMEFA retains useful, permissioned context so the user does not constantly repeat themselves.

## Act

EMEFA uses authorized tools and skills to perform real work.

## Create Opportunities

EMEFA proactively supports customer acquisition and business development.

The product promise can be summarized as:

> **EMEFA understands your business, handles the work you delegate, and helps you create your next opportunities.**

---

# 6. Two Initial Value Engines

EMEFA's early product must focus on two high-value pillars.

## Pillar A — Executive and Administrative Assistance

EMEFA should reduce operational and administrative burden.

Examples:

- email assistance;
- calendar coordination;
- meeting preparation;
- meeting summaries;
- follow-up;
- professional documents;
- reports;
- spreadsheets;
- presentations;
- quotations;
- recurring workflows;
- task and commitment tracking.

The value metric is:

> **Time and cognitive load returned to the user.**

## Pillar B — Business Development

EMEFA should help generate business opportunities continuously.

Examples:

- understand the offer;
- define ideal customer profiles;
- discover prospects;
- research them;
- qualify them;
- prepare personalized outreach;
- manage approval-controlled communication;
- track replies;
- organize follow-up;
- prepare proposals;
- identify next-best commercial actions.

The value metric is:

> **Qualified opportunities created and revenue-supporting work completed.**

---

# 7. The “I Need This” Demonstration

A product demo must not rely only on impressive voice or 3D visuals.

A compelling demonstration should show a painful business problem being solved end-to-end.

Example:

A business owner says:

> “EMEFA, trouve-moi de nouvelles entreprises qui pourraient acheter nos services cette semaine.”

EMEFA:

1. already understands the company;
2. knows the offer;
3. knows the target customer profile;
4. searches authorized sources;
5. identifies prospects;
6. researches them;
7. qualifies them;
8. explains why they fit;
9. prepares personalized outreach;
10. asks for approval where necessary;
11. records follow-up actions.

The reaction we want is not:

> “Wow, the animation is beautiful.”

It is:

> **“If this works reliably, I need it in my business.”**

---

# 8. Product Identity

EMEFA should feel like a real assistant, not a software menu.

Desired qualities:

- calm;
- intelligent;
- capable;
- warm;
- concise;
- context-aware;
- proactive without becoming intrusive;
- occasionally humorous when appropriate;
- trustworthy.

The name EMEFA carries a culturally rooted identity associated with peace/calm.

The assistant should reduce chaos rather than create more notifications and complexity.

---

# 9. JARVIS-Class Presence

The experiential benchmark is the feeling created by advanced fictional assistants such as JARVIS:

- immediate response;
- natural voice;
- interruption;
- spatial/3D presence;
- contextual intelligence;
- smooth transitions;
- proactive assistance;
- clear awareness of ongoing work.

The objective is:

> **JARVIS-class presence with an original EMEFA identity.**

Do not copy copyrighted:

- character identity;
- voice likeness;
- audiovisual assets;
- dialogue;
- logos;
- proprietary interface designs.

The visual experience should communicate assistant state.

Examples:

```text
Listening
Understanding
Planning
Executing
Waiting for Approval
Verifying
Completed
Warning
Failure
```

3D must serve function.

---

# 10. Voice as an Interface, Not the Product

Voice is strategically important because it reduces friction.

A user should be able to say:

> “EMEFA, prépare-moi pour ma réunion de 15 heures.”

instead of navigating multiple applications.

But voice alone is not the value.

The value is what happens after the sentence.

Therefore:

```text
Voice
   ↓
Understanding
   ↓
Context
   ↓
Action
   ↓
Verified Outcome
```

The product must support voice and visual/text interaction together.

---

# 11. Voice Technology Strategy

The existing ElevenLabs implementation should be preserved until alternatives are validated.

The target architecture should avoid permanent dependence on a single end-to-end voice provider.

Preferred direction:

```text
Realtime Transport
      ↓
STT Provider
      ↓
EMEFA Runtime
      ↓
TTS Provider
```

LiveKit should be evaluated as a candidate realtime media/session layer.

STT and TTS should be interchangeable.

Potential product tiers could eventually include:

## Standard Voice

Economical, high-quality default.

## Premium Voice

Higher-cost premium providers such as ElevenLabs when justified.

## African / Local Voice

Specialized speech providers or models optimized for African languages and accents.

No provider choice should be finalized without benchmarks.

---

# 12. African Differentiation

EMEFA should not simply be an international AI product with African branding.

African differentiation must exist in product capability.

Potential differentiation includes:

- local languages;
- African accents;
- code-switching;
- mobile-first workflows;
- bandwidth-conscious operation;
- locally relevant business practices;
- locally used communication channels;
- regional commercial intelligence;
- culturally natural assistant behavior.

A user should eventually be able to speak naturally in a supported local language and ask EMEFA to perform real work.

Example vision:

> A Togolese entrepreneur speaks to EMEFA in Ewe, French, or a natural mixture of languages. EMEFA understands the request, performs the authorized business task, and responds naturally.

This must be validated technically before being marketed as supported.

---

# 13. Conversational Onboarding

The first interaction with EMEFA should feel like meeting a highly competent new assistant.

EMEFA should ask adaptive questions to understand:

- who the user is;
- what their company does;
- products/services;
- customers;
- markets;
- team;
- goals;
- recurring responsibilities;
- preferred communication;
- tools;
- languages;
- autonomy preferences.

The system then builds a structured working profile.

Onboarding must be progressive.

Do not force the user through a giant questionnaire before delivering value.

---

# 14. Relationship and Compounding Value

A strong human assistant becomes valuable partly because they learn:

- preferences;
- people;
- routines;
- terminology;
- priorities;
- recurring workflows;
- communication style.

EMEFA should create the same compounding usefulness.

Over time:

```text
More relevant context
      +
More learned preferences
      +
More connected skills
      +
More workflow knowledge
      ↓
Higher usefulness
```

This creates natural retention.

The goal is not artificial lock-in.

Users must retain control over their data and memory.

---

# 15. Skills

Users should eventually extend EMEFA by giving it Skills.

A Skill is a bounded capability.

Examples:

- email;
- calendar;
- documents;
- spreadsheets;
- presentations;
- CRM;
- research;
- prospecting;
- accounting;
- messaging;
- browser tasks;
- development tools.

Skills may internally use:

- APIs;
- MCP;
- CLIs;
- SDKs;
- workflows;
- browser/computer use;
- external agents.

The user should think:

> “I gave EMEFA the ability to do this.”

not:

> “I configured seven infrastructure protocols.”

---

# 16. Office Work

Office/document creation is a practical high-value capability.

EMEFA should eventually create and edit:

- letters;
- proposals;
- quotations;
- reports;
- Word documents;
- Excel workbooks;
- PowerPoint presentations;
- PDFs.

OfficeCLI is a candidate implementation provider.

It should be integrated behind a stable document capability layer.

Users care about:

> “Prepare the proposal.”

They should not need to know which CLI generated it.

---

# 17. External Specialist Agents

EMEFA may delegate specialized work to systems such as Agent Zero.

The mental model:

> EMEFA is the executive assistant. External agents are specialists EMEFA can call.

EMEFA remains responsible for:

- context;
- permissions;
- delegation;
- verification;
- reporting.

External agents must never become uncontrolled runtime dependencies.

---

# 18. Proactivity

A real assistant does not wait for every instruction.

EMEFA should eventually surface:

- overdue follow-ups;
- important unanswered messages;
- upcoming meetings;
- prospect opportunities;
- deadlines;
- recurring tasks;
- unusual business signals.

Example:

> “Tu as trois prospects importants sans réponse depuis cinq jours. J'ai préparé les relances. Veux-tu que je te les montre ?”

Proactivity must be:

- permissioned;
- configurable;
- useful;
- non-annoying;
- cancellable;
- auditable.

---

# 19. Trust

The more capable EMEFA becomes, the more important trust becomes.

Trust requires:

- clear permissions;
- transparent action status;
- confirmation for consequential actions;
- honest failure reporting;
- verification;
- audit history;
- data control;
- secure credential handling.

EMEFA must never pretend an action succeeded when it did not.

---

# 20. Autonomy Model

Users should choose how much authority EMEFA has.

Levels:

1. Suggest.
2. Prepare.
3. Execute after approval.
4. Execute automatically within scoped rules.
5. Proactively execute within scoped rules.

Example:

A user may authorize:

> “Tu peux automatiquement préparer les relances commerciales, mais demande-moi avant de les envoyer.”

Another may authorize:

> “Pour les prospects qualifiés de catégorie A, tu peux envoyer notre premier message approuvé automatiquement.”

Autonomy must be explicit and revocable.

---

# 21. Multi-Tenant Platform Vision

The long-term product is not one hard-coded EMEFA.

It is a platform.

```text
EMEFA Platform
        ↓
Create Your Assistant
        ↓
Business Onboarding
        ↓
Personality / Voice
        ↓
Memory
        ↓
Skills
        ↓
Permissions
        ↓
Workflows
        ↓
Continuous Learning
```

Each organization gets isolated:

- users;
- assistants;
- memory;
- knowledge;
- credentials;
- skills;
- workflows;
- audit.

---

# 22. Competitive Positioning

EMEFA should not compete only on:

> “Our AI is smarter.”

Foundation models improve rapidly and become commoditized.

Durable differentiation should come from:

## Business Context

Deep understanding of the user's business.

## Memory

Useful accumulated context.

## Execution

Ability to complete real workflows.

## Skills

Extensible capability system.

## Business Development

Continuous opportunity creation.

## African Localization

Languages, accents, workflows, markets.

## Trust

Permissions, audit, verification.

## Experience

A coherent assistant presence instead of fragmented software.

---

# 23. Why EMEFA Is Not Just Another SaaS

Traditional SaaS often requires:

```text
User learns software
→ navigates menus
→ enters data
→ coordinates multiple tools
→ interprets output
→ performs next step
```

EMEFA aims toward:

```text
User states desired outcome
→ EMEFA understands context
→ selects authorized capabilities
→ executes work
→ verifies result
→ reports what matters
```

Existing SaaS products will not simply disappear.

Many will become tools behind agents.

EMEFA should therefore be designed as an orchestration and work layer capable of using existing software rather than attempting to rebuild every business application.

---

# 24. Product Moat

Potential defensibility compounds through:

- personalized memory;
- organizational context;
- workflow history;
- skill ecosystem;
- integrations;
- business-development intelligence;
- local-language capability;
- regional business knowledge;
- trust and reliability;
- accumulated user preferences.

The moat is not one prompt.

The moat is the system.

---

# 25. What EMEFA Must NOT Become

Do not turn EMEFA into:

## A generic chatbot

Conversation without execution is insufficient.

## A flashy 3D demo

Visual spectacle without business value is insufficient.

## A spam machine

Prospecting must prioritize relevance and responsible outreach.

## A giant autonomous black box

Users need control and visibility.

## A wrapper around one provider

No permanent unnecessary dependency on ElevenLabs, Claude, Agent Zero, or any single vendor.

## An everything-at-once platform

Prioritize painful workflows first.

## A clone of JARVIS

Use the experiential benchmark, create an original product identity.

---

# 26. Product Prioritization Formula

Prioritize features using:

```text
Value =
Pain Severity
× Frequency
× Measurable Outcome
× Reliability Potential
÷ Complexity
```

High-priority examples:

- customer acquisition;
- follow-up;
- executive briefings;
- document creation;
- meeting preparation;
- repetitive administration.

Lower priority initially:

- novelty animations with no workflow value;
- huge skill marketplace before core skills work;
- excessive multi-agent complexity;
- features users rarely need.

---

# 27. North Star Outcome

The ultimate product outcome is:

> **EMEFA gives a small organization leverage that previously required additional administrative and commercial staff, while keeping the human owner in control.**

This does not mean replacing all employees.

It means increasing the amount of useful work a person or small team can reliably accomplish.

---

# 28. Success Metrics

Metrics should eventually include:

## Activation

- onboarding completion;
- first connected skill;
- first successfully completed task;
- time to first value.

## Engagement

- weekly active assistants;
- meaningful delegated tasks;
- voice/text sessions tied to completed work.

## Administrative Value

- tasks completed;
- estimated hours saved;
- documents produced;
- follow-ups completed.

## Business Development

- qualified prospects discovered;
- outreach prepared/approved;
- follow-ups completed;
- meetings/opportunities generated.

## Trust

- successful action rate;
- verification rate;
- failure recovery;
- approval rejection rate;
- incorrect-action incidents.

## Retention

- active organizations;
- recurring workflows;
- memory usefulness;
- skill adoption.

Avoid vanity metrics such as raw message count.

---

# 29. Initial Hero Workflows

## Hero Workflow 1 — Executive Morning Brief

> “EMEFA, qu'est-ce qui demande mon attention aujourd'hui ?”

EMEFA synthesizes authorized:

- calendar;
- communications;
- commitments;
- tasks;
- prospect follow-ups.

## Hero Workflow 2 — Prospecting

> “Trouve-moi de nouveaux clients potentiels correspondant à notre cible.”

EMEFA:

- discovers;
- researches;
- qualifies;
- explains;
- prepares next actions.

## Hero Workflow 3 — Professional Proposal

> “Prépare une proposition pour cette entreprise.”

EMEFA:

- retrieves business/client context;
- drafts;
- applies company standards;
- generates professional document;
- verifies output.

## Hero Workflow 4 — Meeting Preparation

> “Prépare-moi pour ma réunion avec X.”

EMEFA retrieves relevant context and creates a briefing.

## Hero Workflow 5 — Follow-Up

> “Qui dois-je relancer cette semaine ?”

EMEFA identifies authorized follow-up obligations and prepares actions.

---

# 30. MVP Philosophy

The MVP must not attempt the full end-state vision.

The MVP must prove:

1. EMEFA understands meaningful business context.
2. EMEFA remembers relevant preferences.
3. EMEFA can use real tools safely.
4. EMEFA completes useful workflows.
5. Voice interaction is natural enough to reduce friction.
6. Administrative work saves time.
7. Business-development workflows create measurable value.
8. Users trust EMEFA enough to delegate again.

---

# 31. Product Development Sequence

The exact roadmap must follow the current-state audit, but strategic order is:

```text
Audit Existing Product
        ↓
Harden Foundations
        ↓
Understand User/Business
        ↓
Memory
        ↓
Skills/Tools
        ↓
Administrative Vertical Slice
        ↓
Business Development Vertical Slice
        ↓
Proactivity
        ↓
Voice Cost/Architecture Optimization
        ↓
African Language Expansion
        ↓
Multi-Tenant Platformization
        ↓
Skill Ecosystem
```

Do not blindly rebuild working existing capabilities.

---

# 32. The Long-Term Experience

A mature EMEFA interaction might look like:

> **User:** “EMEFA, fais-moi le point.”

EMEFA understands the user means a business briefing.

It responds naturally:

- two priority customer messages need attention;
- tomorrow's meeting requires preparation;
- three qualified prospects are ready for review;
- one proposal deadline is approaching;
- a weekly report has been prepared.

The user says:

> “Occupe-toi de ce que tu peux et montre-moi ce qui demande mon accord.”

EMEFA executes authorized tasks, prepares approval-required actions, verifies results, and reports concisely.

That is the product.

Not a chatbot.

Not a collection of buttons.

A working relationship between a person and a capable digital assistant.

---

# 33. Final Product Principle

Every product decision should answer:

> **Does this make EMEFA more useful as a trusted assistant that understands the business and gets valuable work done?**

If not, it is probably not the priority.

The desired end state is:

> **An entrepreneur should feel that EMEFA knows their business, understands how they work, is available whenever needed, speaks naturally, handles administrative burden, continuously helps create opportunities, and can gain new skills as their needs evolve.**

That is the product vision.
