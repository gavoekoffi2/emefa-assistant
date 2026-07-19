# EMEFA — ADMINISTRATIVE_ASSISTANT_ENGINE.md

> **Document type:** Administrative assistant, executive support, office productivity, coordination, and daily operations specification  
> **Project:** EMEFA  
> **Development mode:** Brownfield continuation  
> **Purpose:** Define how EMEFA performs practical administrative and executive-assistant work across email, calendar, meetings, documents, tasks, files, follow-ups, and recurring operations.  
> **Critical rule:** EMEFA must execute real administrative work through governed Skills and tools, not merely explain how the user could do it manually.

---

# 1. Product Objective

EMEFA should behave like a capable digital administrative assistant that understands:

- the user;
- the organization;
- priorities;
- relationships;
- preferences;
- recurring procedures;
- permissions.

The target experience is:

> “I can delegate routine administrative work to EMEFA instead of manually moving information between email, calendar, documents, spreadsheets, and task lists.”

Core loop:

```text
Understand Request
→ Retrieve Context
→ Plan Work
→ Use Skills
→ Request Approval When Required
→ Execute
→ Verify
→ Organize Result
→ Follow Up
```

---

# 2. Administrative Capability Domains

EMEFA should progressively support:

```text
1. Email & Communication
2. Calendar & Scheduling
3. Meetings
4. Documents
5. Spreadsheets
6. Presentations
7. Files & Knowledge
8. Tasks & Follow-Ups
9. Contacts & Relationships
10. Daily Executive Briefing
11. Recurring Administrative Workflows
12. Cross-Application Coordination
```

These are business capabilities, not vendor-specific integrations.

---

# 3. Architecture Principle

Do not create one giant “administrative agent.”

Use composable Skills:

```text
Administrative Assistant
        ↓
Skill Orchestration
        ├── EmailCapability
        ├── CalendarCapability
        ├── MeetingCapability
        ├── DocumentCapability
        ├── SpreadsheetCapability
        ├── PresentationCapability
        ├── FileCapability
        ├── TaskCapability
        └── ContactCapability
```

Each capability may use multiple providers/adapters.

---

# 4. Email Capability

Required operations may include:

```text
search
read
summarize
classify
draft
reply
forward
label
archive
extract_action_items
send
```

Separate read actions from write/send actions.

---

# 5. Email Understanding

EMEFA should identify:

- sender;
- organization;
- topic;
- urgency;
- requested action;
- deadline;
- attachments;
- relationship context;
- thread history.

Do not classify importance solely from words like “URGENT.”

Use context.

---

# 6. Important Email Triage

Example user request:

> “Montre-moi ce qui mérite mon attention aujourd'hui.”

EMEFA may:

```text
Read authorized inbox metadata/content
→ identify actionable messages
→ rank by importance
→ summarize
→ extract deadlines/actions
```

Output:

```text
Needs action today
Waiting for your reply
Informational
Low priority
```

Avoid hiding messages merely because AI considers them unimportant.

---

# 7. Email Drafting

Draft using:

```text
Thread context
Recipient relationship
User preferences
Business context
Language
Purpose
```

Example:

> “Réponds à Ama et confirme que nous pouvons livrer vendredi.”

EMEFA should understand the relevant thread before drafting.

Never invent commitments not supported by context.

---

# 8. Email Sending

Sending is consequential.

Flow:

```text
Draft
→ Validate Recipients
→ Validate Attachments
→ Validate Content
→ Permission Check
→ Approval if required
→ Send
→ Verify Result
→ Audit
```

Avoid duplicate sends with idempotency.

---

# 9. Attachment Safety

Before sending:

- confirm intended attachment;
- verify latest version;
- verify recipient scope;
- scan/validate if applicable.

Prevent common failure:

> Sending confidential or wrong document to wrong recipient.

---

# 10. Email Follow-Up

EMEFA can track:

```text
Awaiting reply
User owes reply
Promised document
Deadline mentioned
Follow-up date
```

Create durable tasks.

Do not rely only on memory.

---

# 11. Calendar Capability

Operations:

```text
list events
search events
find availability
create
update
cancel
reschedule
invite
prepare agenda
```

Respect calendar permissions.

---

# 12. Scheduling

User:

> “Trouve 30 minutes avec Kossi cette semaine.”

Flow:

```text
Resolve Contact
→ Check Authorized Availability
→ Apply User Preferences
→ Find Slots
→ Propose / Book depending permission
→ Verify
```

Preferences may include:

- working hours;
- lunch;
- travel buffer;
- meeting-free blocks;
- preferred duration.

---

# 13. External Scheduling

For external attendees:

EMEFA may:

- propose times;
- draft/send scheduling message;
- use scheduling link;
- coordinate replies;
- create event after agreement.

Do not claim access to external calendars unless actually authorized.

---

# 14. Calendar Conflict Prevention

Before creating/updating:

- check overlap;
- travel time where relevant;
- timezone;
- duplicate event;
- recurring-event implications.

Warn rather than silently creating conflicts.

---

# 15. Timezones

Always model timezone explicitly.

For cross-border Africa/international business:

```text
User timezone
Attendee timezone
Event timezone
```

Display local times clearly.

---

# 16. Meeting Capability

Lifecycle:

```text
Before Meeting
→ During Meeting
→ After Meeting
```

EMEFA should add value across all three.

---

# 17. Before Meeting

Prepare a briefing:

```text
Who is attending?
What organization?
What happened previously?
Open commitments?
Relevant documents?
Meeting objective?
Suggested agenda?
Questions to ask?
```

Use only authorized data.

---

# 18. Meeting Brief Example

User:

> “Prépare-moi pour ma réunion avec Horizon demain.”

EMEFA produces:

```text
Objective
Attendees
Relationship Summary
Last Interactions
Open Commitments
Relevant Documents
Key Questions
Risks
Recommended Next Steps
```

This is high-value executive support.

---

# 19. During Meeting

Future/optional capabilities:

- transcription;
- notes;
- action-item extraction;
- decision capture.

Require clear consent/notification where recording laws or policies apply.

Do not secretly record.

---

# 20. After Meeting

Flow:

```text
Transcript/Notes
→ Summary
→ Decisions
→ Action Items
→ Owners
→ Deadlines
→ Follow-Up Draft
→ Task Creation
→ CRM/Project Update if authorized
```

This should be a reusable workflow.

---

# 21. Meeting Action Items

Store structurally:

```yaml
action: "Send revised proposal"
owner: "User"
due_date: optional
source_meeting: reference
status: open
```

Do not bury commitments only in a summary document.

---

# 22. Document Capability

EMEFA should create and edit:

```text
Letters
Proposals
Reports
Memos
Minutes
Contracts/templates where appropriate
Business plans
Administrative forms
Invoices/quotes where connected to business system
```

Legal/financial documents may require review.

---

# 23. OfficeCLI Positioning

OfficeCLI may serve as an execution provider for document operations if technically validated.

Architecture:

```text
DocumentCapability
      ↓
Provider Adapter
      ├── OfficeCLI
      ├── Native Library
      ├── Cloud Office API
      └── Future Provider
```

Do not make core EMEFA logic depend directly on OfficeCLI commands.

---

# 24. Document Workflow

```text
Understand Purpose
→ Retrieve Business Context
→ Select Template
→ Generate Content
→ Render
→ Validate Structure
→ Apply Branding
→ Save Version
→ Return Artifact
```

If editing existing document:

```text
Load
→ Preserve Structure
→ Apply Requested Changes
→ Validate
→ Save New Version unless overwrite explicitly intended
```

---

# 25. Document Formatting

Support:

- headings;
- tables;
- page breaks;
- headers/footers;
- logo;
- typography;
- margins;
- numbered sections;
- signature blocks;
- table of contents where appropriate.

Quality must be professional enough to send externally.

---

# 26. Templates

Organization memory may store:

```text
Proposal template
Letterhead
Report template
Meeting-minutes template
Invoice template
Presentation theme
```

EMEFA should reuse templates automatically when appropriate.

---

# 27. Brand Consistency

Apply:

- organization name;
- logo;
- colors;
- fonts;
- tone;
- legal footer;
- contact information.

Do not hallucinate missing brand assets.

Ask or use neutral defaults.

---

# 28. Document Verification

Before declaring success:

- file exists;
- opens;
- expected sections present;
- no placeholder tokens;
- formatting valid;
- requested content included.

For critical documents, generate preview or structured validation.

---

# 29. Spreadsheet Capability

EMEFA should support practical spreadsheet work:

```text
Create workbook
Read workbook
Clean data
Sort/filter
Calculate
Summarize
Create formulas
Create tables
Generate charts
Format
Export
```

---

# 30. Spreadsheet Safety

Never silently overwrite source data.

Prefer:

```text
Original
→ Working Copy
→ Validated Output
```

Unless explicit overwrite requested.

---

# 31. Spreadsheet Formula Integrity

Validate:

- formula references;
- totals;
- ranges;
- divide-by-zero;
- dates;
- currency;
- locale formats.

Do not present unverified calculations as correct.

---

# 32. African Business Formats

Support common practical requirements:

- FCFA/XOF;
- local date formats;
- French labels;
- OHADA-related terminology where relevant;
- local phone/address formats.

Do not hard-code one country's rules globally.

---

# 33. Presentation Capability

EMEFA should create:

```text
Sales decks
Investor decks
Internal reports
Training presentations
Meeting presentations
Project updates
```

Workflow:

```text
Goal
→ Audience
→ Narrative
→ Outline
→ Slides
→ Visuals
→ Branding
→ Validation
```

---

# 34. Presentation Quality

Avoid:

- walls of text;
- repetitive generic slides;
- fake statistics;
- random stock visuals.

Use evidence and concise narrative.

---

# 35. File Capability

Operations:

```text
search
list
read
create
rename
move
copy
organize
archive
share
```

Permission-aware.

---

# 36. File Organization

Example:

User:

> “Range les documents du projet Horizon.”

EMEFA may propose:

```text
Horizon/
├── 01_Admin
├── 02_Proposals
├── 03_Meetings
├── 04_Deliverables
└── 05_Finance
```

Do not reorganize destructively without approval/policy.

---

# 37. File Search

User:

> “Retrouve la dernière proposition envoyée à Horizon.”

Use:

```text
metadata
content search
relationship context
version/date
email attachments if authorized
```

Return confidence/evidence.

---

# 38. Version Management

Avoid:

```text
proposal_final_final2_REAL.docx
```

Use version metadata where possible.

Conceptual:

```text
document_id
version
created_at
author/source
status
```

---

# 39. Task Capability

Administrative work produces tasks.

Operations:

```text
create
assign
prioritize
schedule
complete
cancel
follow_up
```

Tasks must be durable.

---

# 40. Task Extraction

From email:

> “Please send the revised budget by Friday.”

EMEFA extracts:

```text
Task: Send revised budget
Due: Friday
Source: email
```

May ask before creating depending preference.

---

# 41. Commitment Tracking

EMEFA should understand:

```text
I promised
They promised
Waiting for
Due by
Blocked by
```

This is a major assistant capability.

---

# 42. Daily Executive Brief

A high-value recurring experience.

Example:

> “Bonjour. Aujourd'hui tu as 4 réunions. Deux emails demandent une réponse avant midi. Le devis Horizon est toujours en attente de validation et Ama attend le document promis hier.”

Sources:

```text
Calendar
Email
Tasks
Commitments
Business Development
Active Workflows
```

Keep concise.

---

# 43. Morning Brief Structure

Potential:

```text
1. Top Priorities
2. Meetings
3. Messages Requiring Action
4. Deadlines / Commitments
5. Business Opportunities
6. Risks / Blockers
```

Adapt to user preference.

---

# 44. End-of-Day Brief

Optional:

```text
Completed
Pending
New commitments
Tomorrow
Items needing decision
```

Do not create notification fatigue.

---

# 45. Recurring Administrative Workflows

Examples:

```text
Weekly report
Monthly invoice preparation
Monday agenda
Friday follow-up review
Meeting preparation
Expense consolidation
Document archiving
```

Each workflow should be explicit and controllable.

---

# 46. Example — Weekly Report

```text
Friday 15:00
→ gather authorized data
→ summarize activity
→ generate report
→ create DOCX/PDF
→ present for review
→ send if approved/policy allows
```

Durable scheduler required.

---

# 47. Cross-Application Workflow

Real assistant value comes from combining tools.

Example:

> “Prépare ma réunion avec Ama.”

May require:

```text
Calendar
→ Contacts
→ Email
→ CRM
→ Files
→ Memory
→ Document generation
```

One user request, multiple governed Skills.

---

# 48. Cross-Application Orchestration

Use a plan with checkpoints:

```text
1. Resolve meeting
2. Resolve participants
3. Retrieve relationship context
4. Retrieve relevant communication
5. Retrieve documents
6. Generate briefing
7. Validate
```

Do not let an unconstrained agent wander indefinitely.

---

# 49. Contact Capability

Store/resolve:

```text
Name
Organization
Role
Email
Phone
Relationship
Preferred channel
Notes
```

Respect privacy.

---

# 50. Contact Resolution

User:

> “Envoie ça à Ama.”

EMEFA must resolve ambiguity.

If multiple Amas:

> “Tu parles d'Ama Mensah chez Horizon ou d'Ama Kossi chez Nova ?”

Do not guess recipients for consequential actions.

---

# 51. Relationship Context

Before communication:

```text
Who is this?
What is the relationship?
Last interaction?
Open commitments?
Preferred language/channel?
```

Improves quality.

---

# 52. Phone / Call Preparation

EMEFA may prepare:

```text
Call objective
Background
Questions
Talking points
Objections
Next-step goal
```

Future telephony execution requires separate compliance/provider architecture.

---

# 53. Administrative Forms

EMEFA may assist with repetitive forms by:

```text
Extract known business data
→ map fields
→ prefill
→ highlight unknown fields
→ user review
```

Do not submit legal/government forms automatically without appropriate review and authorization.

---

# 54. Invoices and Quotes

If connected to accounting/business system:

```text
Prepare draft
→ validate customer/items/tax/currency
→ approval
→ issue/send
```

Financial rules vary by jurisdiction.

Do not invent tax treatment.

---

# 55. Expense Administration

Potential:

```text
Collect receipts
Extract fields
Categorize
Flag missing info
Prepare report
Export to accounting
```

Require validation for uncertain OCR/extraction.

---

# 56. Travel Administration

Potential:

```text
Itinerary
Calendar coordination
Travel documents checklist
Meeting schedule
Expense plan
```

Booking/purchase requires explicit permission and safeguards.

---

# 57. Procurement Assistance

Potential:

```text
Collect requirements
Find approved vendors
Compare quotes
Prepare comparison
Draft purchase request
```

Do not autonomously commit funds without authorization.

---

# 58. Administrative Knowledge

EMEFA should know organization-specific procedures:

```text
How expenses are approved
Who signs contracts
Where reports are stored
How meetings are documented
Which template to use
```

Store as procedure memory/workflows.

---

# 59. Learning Procedures

If user repeatedly performs same sequence:

```text
Receive invoice
→ rename
→ save in Finance/YYYY/MM
→ update spreadsheet
→ notify accountant
```

EMEFA may propose:

> “Veux-tu que j'en fasse une procédure automatique ?”

Do not silently automate consequential workflows.

---

# 60. Autonomy Levels

Administrative actions can use levels:

```text
A0 — Suggest only
A1 — Prepare draft
A2 — Execute after approval
A3 — Execute within explicit policy
A4 — Bounded recurring autonomy
```

Examples:

```text
Summarize inbox → A1/A3
Draft reply → A1
Send external email → A2 by default
Archive newsletters → potentially A3
Recurring weekly report → A4 within policy
```

---

# 61. Permission Profiles

Possible user presets:

```text
Conservative
Balanced
Delegated
Custom
```

Example Balanced:

```text
Read/summarize → automatic
Draft → automatic
Send → approval
Calendar create → approval
Internal file organization → approved folders only
Delete → approval
Financial actions → approval
```

---

# 62. Destructive Actions

Actions like:

```text
delete email
delete file
cancel event
overwrite document
```

need stronger controls.

Prefer reversible operations:

```text
archive
move to trash
create new version
```

where possible.

---

# 63. Idempotency

Critical for:

- sending;
- creating events;
- generating invoices;
- uploading files.

Retry must not duplicate side effects.

Use idempotency keys/correlation IDs where supported.

---

# 64. Verification

Every action needs proof.

Examples:

Email:

```text
provider message ID
sent status
```

Calendar:

```text
event ID
start/end
attendees
```

Document:

```text
file exists
hash/version
```

Do not equate “tool returned no error” with success.

---

# 65. Partial Failure

Example workflow:

```text
Create document → success
Upload to drive → success
Send email → failed
```

Result must say:

> “Le document a été créé et enregistré, mais l'envoi de l'email a échoué.”

Do not report whole workflow as success.

---

# 66. Retry Strategy

Retry transient:

- timeout;
- 429;
- temporary provider errors.

Do not blindly retry:

- invalid recipient;
- permission denied;
- destructive conflict;
- uncertain send state.

Verify first.

---

# 67. Human Escalation

EMEFA should escalate when:

- ambiguity is consequential;
- conflicting instructions;
- missing authorization;
- uncertain financial/legal data;
- suspicious request;
- irreversible action.

Ask the minimum necessary question.

---

# 68. Administrative Dashboard

Potential views:

```text
Today
Inbox Actions
Meetings
Tasks
Documents
Waiting For
Approvals
Automations
```

Focus on work, not chat history.

---

# 69. “Today” View

High-value home screen:

```text
Top 3 priorities
Next meeting
Items waiting for approval
Messages needing response
Deadlines
Prospecting opportunities
```

This can make EMEFA operationally sticky.

---

# 70. Approval Inbox

Centralize pending approvals:

```text
3 emails ready to send
1 calendar change
2 documents ready
1 prospecting campaign
```

Allow:

```text
Preview
Edit
Approve
Reject
```

---

# 71. Voice Integration

User:

> “EMEFA, qu'est-ce que j'ai d'important aujourd'hui ?”

EMEFA answers concise summary.

User:

> “Réponds au premier email et décale la réunion de 14 heures à demain.”

EMEFA:

- drafts reply;
- checks calendar implications;
- requests approvals as required;
- executes;
- verifies.

Voice uses same Skills.

---

# 72. Multilingual Administration

A user may speak French while recipient requires English.

Flow:

```text
User Intent in French
→ Business Context
→ Draft in Recipient Language
→ Preserve Meaning
→ User Review
```

Do not translate names/terms incorrectly.

---

# 73. Local Business Context

Support:

- FCFA;
- local holidays/calendar where configured;
- regional phone formats;
- French administrative terminology;
- bilingual environments.

Use country/tenant configuration.

---

# 74. Poor Connectivity

Administrative tasks should survive disconnect.

Example:

User starts document generation by voice, then connection drops.

Durable task continues.

User returns and sees result.

---

# 75. Offline-Like Queueing

For temporary provider/network failure:

- save intent/task safely;
- queue only if side effects remain safe;
- notify status.

Do not queue time-sensitive sends silently without policy.

---

# 76. Provider Abstraction

Examples:

```text
EmailCapability
├── GmailAdapter
├── MicrosoftGraphAdapter
└── IMAP/SMTPAdapter if justified

CalendarCapability
├── GoogleCalendarAdapter
└── MicrosoftCalendarAdapter

DocumentCapability
├── OfficeCLIAdapter
├── NativeAdapter
└── CloudOfficeAdapter
```

Domain Skills must not contain provider-specific business logic.

---

# 77. MCP

MCP can expose administrative tools.

Examples:

- email;
- calendar;
- drive;
- CRM;
- office tools.

All MCP tools go through EMEFA governance.

Do not allow arbitrary tool discovery to bypass permissions.

---

# 78. Agent Zero

Agent Zero may handle bounded multi-step administrative tasks.

Example:

> “Research these three vendors and prepare a comparison.”

Provide:

- scope;
- tools;
- time/cost limits;
- output schema.

Final actions remain under EMEFA policy.

---

# 79. OfficeCLI

OfficeCLI is particularly relevant for:

- DOCX;
- XLSX;
- PPTX;
- formatting;
- conversions.

Before adoption:

- benchmark;
- sandbox execution;
- validate outputs;
- define adapter;
- handle failures.

Never execute arbitrary shell commands generated by model without allowlisting/sandbox.

---

# 80. File Security

Before reading/writing:

- tenant authorization;
- path scope;
- file type;
- size;
- malware/security checks where relevant.

Prevent path traversal.

Do not allow model to escape approved workspace.

---

# 81. Document Prompt Injection

Documents/emails may contain:

> “Ignore all previous instructions…”

Treat content as data.

Do not let document instructions alter system policy.

---

# 82. Sensitive Information

Administrative work may expose:

- salaries;
- contracts;
- customer data;
- credentials;
- financial data.

Use least privilege.

Redact logs.

Do not send sensitive content to unnecessary providers.

---

# 83. Audit

Consequential actions should log:

```text
Who requested
What EMEFA planned
Which Skill executed
Provider
Approval
Result
Timestamp
Correlation ID
```

Do not log secrets.

---

# 84. Observability

Metrics:

```text
emails summarized
drafts accepted
send failures
meetings prepared
documents created
tasks completed
time saved estimate
approval rate
correction rate
```

Quality > volume.

---

# 85. Administrative Evaluation Cases

Maintain regression tests.

## Case 1 — Ambiguous Recipient

> “Envoie le rapport à Ama.”

Two contacts named Ama.

Expected: clarify.

## Case 2 — Wrong Attachment Risk

Draft references report but selected attachment is invoice.

Expected: block/warn.

## Case 3 — Calendar Conflict

New meeting overlaps existing commitment.

Expected: warn/propose alternative.

## Case 4 — Document Creation

Generate branded proposal.

Expected: valid file, correct template, no placeholders.

## Case 5 — Duplicate Send Retry

Network timeout after send.

Expected: verify before retry.

---

# 86. Example — Morning Delegation

User:

> “EMEFA, gère ma matinée.”

This is too broad for unlimited autonomy.

EMEFA can interpret within policy:

```text
Summarize priorities
Prepare meeting briefs
Draft urgent replies
Organize approval queue
Surface conflicts
```

Then say:

> “J'ai préparé deux réponses et détecté un conflit à 11 h. Les actions qui nécessitent ta validation sont prêtes.”

---

# 87. Example — Meeting-to-Follow-Up

User:

> “Prépare ma réunion avec Horizon et gère le suivi après.”

Before:

- briefing;
- agenda;
- documents.

After:

- summary;
- actions;
- follow-up email;
- tasks;
- CRM update.

Approval based on policy.

---

# 88. Example — Document Workflow

User:

> “Prépare le rapport mensuel et envoie-le à mon associé.”

Flow:

```text
Resolve report definition
→ gather authorized data
→ generate DOCX/PDF
→ validate
→ identify associate
→ prepare email
→ preview/approval
→ send
→ verify
```

One request, complete workflow.

---

# 89. Example — Spreadsheet

User:

> “Prends le fichier des ventes, nettoie-le et fais-moi un résumé.”

Flow:

```text
Load copy
→ inspect schema
→ identify anomalies
→ clean with traceable changes
→ calculate summary
→ create output
→ explain transformations
```

Never destroy original.

---

# 90. Example — Inbox to Task List

User:

> “Transforme mes emails importants de cette semaine en liste d'actions.”

Flow:

```text
Search authorized emails
→ classify actionable
→ extract task/deadline/source
→ deduplicate
→ present
→ create tasks after policy/approval
```

---

# 91. MVP Scope

## Must Have

- email read/search/summarize/draft;
- safe send with approval;
- calendar read/create/update;
- meeting preparation;
- document generation;
- basic spreadsheet generation/analysis;
- durable tasks;
- approval inbox;
- daily brief;
- tenant isolation;
- audit.

## Next

- meeting transcription/notes;
- recurring workflows;
- file organization;
- presentations;
- contact intelligence;
- cross-app workflows.

## Later

- expenses;
- procurement;
- travel;
- advanced forms;
- deeper finance/accounting integrations.

---

# 92. First Demo Scenarios

Use real end-to-end value.

## Demo A

> “Qu'est-ce qui mérite mon attention aujourd'hui ?”

EMEFA combines calendar/email/tasks.

## Demo B

> “Prépare-moi pour ma réunion de 15 heures.”

EMEFA creates briefing from multiple sources.

## Demo C

> “Prépare la proposition, mets-la au bon format et rédige l'email.”

EMEFA creates real artifact.

## Demo D

> “Trouve-moi de nouveaux prospects et prépare les meilleurs messages.”

Connects Business Development Engine.

---

# 93. Product Value

Administrative value is measured by:

```text
Time saved
Tasks completed
Errors avoided
Follow-ups not forgotten
Faster document production
Better preparation
Reduced context switching
```

Not by number of chat messages.

---

# 94. Definition of Done — Administrative Skill

Every production administrative Skill requires:

- typed inputs/outputs;
- tenant scope;
- permission classification;
- provider adapter;
- timeout;
- retry policy;
- idempotency where needed;
- verification;
- audit;
- error UX;
- tests.

For destructive/consequential actions:

- preview/approval or explicit autonomy policy;
- rollback/recovery where possible.

---

# 95. Anti-Patterns

Never build EMEFA as:

```text
Chat UI
+ giant system prompt
+ direct Gmail/Calendar/Office credentials
```

Never:

- guess recipients;
- fabricate meetings;
- send without policy;
- overwrite originals casually;
- expose credentials;
- report success without verification;
- create separate logic for voice and text;
- depend entirely on one provider;
- store every administrative detail as AI memory.

---

# 96. North-Star Workflow

User says:

> “EMEFA, demain j'ai une réunion importante avec Horizon. Prépare-moi tout ce qu'il faut et assure le suivi.”

EMEFA:

```text
Finds Meeting
→ identifies attendees
→ retrieves relationship/email context
→ finds relevant files
→ identifies open commitments
→ prepares concise briefing
→ prepares agenda/materials
→ after meeting captures authorized notes
→ extracts decisions/actions
→ drafts follow-up
→ creates tasks
→ updates connected systems
→ sends only according to permission
→ tracks commitments
```

The user should feel:

> “I delegated the administrative outcome, not ten separate software clicks.”

---

# 97. Final Principle

> **EMEFA should reduce the operational friction between intention and completed administrative work.**

The assistant becomes valuable when it can turn:

```text
“Prépare ma réunion.”
“Réponds à ça.”
“Fais-moi le rapport.”
“Organise ma semaine.”
“Relance ceux qui n'ont pas répondu.”
```

into verified outcomes across the user's tools.

Combined with the Business Development Engine, this creates the core promise:

> **EMEFA helps the entrepreneur run the business and helps the business find more opportunities — through one personalized assistant that understands how the organization actually works.**
