# EMEFA — AUTONOMY_AND_WORKFLOWS.md

> **Document type:** Autonomous execution, durable workflows, background jobs, approvals, scheduling, recovery, and orchestration specification  
> **Project:** EMEFA  
> **Development mode:** Brownfield continuation  
> **Purpose:** Define how EMEFA moves from conversational assistance to reliable autonomous work without becoming an uncontrolled agent.  
> **Critical rule:** Autonomy must be bounded by explicit permissions, budgets, durable state, verification, and human control.

---

# 1. Product Objective

EMEFA should not require the user to remain in a chat window while every task is executed.

The user should be able to say:

> “Chaque semaine, trouve-moi dix nouveaux prospects sérieux et prépare les messages.”

or:

> “Prépare mon rapport mensuel le dernier vendredi du mois.”

or:

> “Surveille les réponses à cette campagne et prépare les suivis.”

EMEFA should then:

```text
Understand Goal
→ Build/Select Workflow
→ Check Permissions
→ Schedule/Start
→ Execute in Background
→ Persist State
→ Handle Failures
→ Request Approval at Defined Checkpoints
→ Verify Results
→ Notify User
→ Learn From Outcome
```

---

# 2. Autonomy Is Not Unlimited Agency

Do not implement:

```text
User Goal
→ LLM has unrestricted tools
→ runs until it thinks it is done
```

Implement:

```text
Goal
→ Bounded Plan
→ Policy
→ Durable Workflow
→ Typed Skills
→ Budgets
→ Checkpoints
→ Verification
→ Result
```

Autonomy is controlled execution.

---

# 3. Core Concepts

```text
Task
Workflow
Step
Skill
Trigger
Schedule
Policy
Approval
Budget
Artifact
Event
Result
```

Keep these concepts distinct.

---

# 4. Task vs Workflow

## Task

A concrete unit of work.

Example:

> “Prepare tomorrow's meeting brief.”

## Workflow

A reusable multi-step process.

Example:

```text
Resolve Meeting
→ Retrieve Context
→ Retrieve Documents
→ Generate Brief
→ Validate
→ Notify
```

A workflow may create many tasks.

---

# 5. Workflow Definition

Conceptual:

```yaml
id: string
tenant_id: string
name: string
version: integer

trigger:
  type: manual|schedule|event|condition

inputs: {}
steps: []

policy:
  autonomy_level: A0-A4
  approvals: []
  budgets: {}

status: draft|active|paused|archived

created_at: datetime
updated_at: datetime
```

---

# 6. Workflow Run

Each execution must have durable state.

```yaml
run_id: string
workflow_id: string
workflow_version: integer
tenant_id: string
status: string
started_at: datetime
updated_at: datetime
completed_at: optional

current_step: optional
inputs: {}
outputs: {}
artifacts: []
errors: []
correlation_id: string
```

Never depend only on process memory.

---

# 7. Run States

Recommended:

```text
CREATED
PLANNING
READY
RUNNING
WAITING
AWAITING_APPROVAL
PAUSED
RETRYING
VERIFYING
COMPLETED
PARTIAL_SUCCESS
FAILED
CANCELLED
```

Transitions must be explicit.

---

# 8. Step States

```text
PENDING
READY
RUNNING
WAITING
SUCCEEDED
FAILED
SKIPPED
CANCELLED
```

Store timestamps and attempt count.

---

# 9. Durable Execution

Long-running work must survive:

- browser close;
- voice disconnect;
- application restart;
- worker restart;
- network interruption;
- provider timeout.

The execution engine must resume from durable state.

Do not rely on one long HTTP request.

---

# 10. Workflow Engine Decision

Claude must audit existing infrastructure before selecting technology.

Possible approaches:

- existing queue/job system;
- durable workflow engine;
- database-backed orchestrator;
- Temporal or equivalent;
- framework already present in repository.

Create ADR.

Do not add a complex workflow platform unless justified.

---

# 11. Autonomy Levels

Standardize:

```text
A0 — Suggest
A1 — Prepare
A2 — Execute After Approval
A3 — Execute Within Explicit Policy
A4 — Bounded Recurring Autonomy
```

## A0

EMEFA recommends only.

## A1

EMEFA prepares artifact/action but does not execute side effect.

## A2

EMEFA waits for approval before action.

## A3

EMEFA may execute actions matching explicit policy.

## A4

EMEFA may repeatedly execute a bounded workflow according to schedule/conditions and policy.

No hidden A5 “do anything.”

---

# 12. Autonomy Is Per Capability

A user may allow:

```text
Email drafting: A3
Email sending: A2
Calendar scheduling: A2
Prospect research: A4
Prospect outreach: A2
File organization: A3
Payments: A0/A1
```

Do not assign one global autonomy level to the entire assistant.

---

# 13. Policy Model

Conceptual:

```yaml
subject:
  user_id: string

capability: "email.send"

scope:
  recipients: optional
  domains: optional
  max_per_day: optional

autonomy_level: A2

constraints:
  require_preview: true
  max_batch_size: 10

valid_from: optional
valid_until: optional
```

Policies must be explicit and inspectable.

---

# 14. Approval Checkpoints

A workflow can pause:

```text
Research
→ Draft
→ [APPROVAL]
→ Send
→ Verify
```

Approval binds to:

- exact action;
- scope;
- recipients;
- artifact version;
- amount/impact;
- expiration where appropriate.

Do not reuse approval after material changes.

---

# 15. Approval Object

Conceptual:

```yaml
approval_id: string
run_id: string
step_id: string

action_summary: string
action_hash: string
risk_level: string

requested_at: datetime
expires_at: optional

status: pending|approved|rejected|expired
approved_by: optional
```

---

# 16. Material Change Invalidates Approval

If approved:

```text
Send email to 5 recipients
```

then workflow changes to:

```text
Send email to 50 recipients
```

old approval is invalid.

Same for:

- changed attachment;
- changed amount;
- changed recipient;
- changed schedule;
- changed content materially.

---

# 17. Approval Inbox

Central UI:

```text
Approvals
├── Emails ready to send
├── Calendar changes
├── Documents
├── Prospecting outreach
└── High-risk actions
```

Each item shows:

- what;
- why;
- impact;
- preview;
- source workflow.

---

# 18. Bulk Approval

Allow carefully:

```text
Approve these 10 messages
```

Show batch scope.

Do not hide heterogeneous high-risk actions in one bulk approval.

---

# 19. Scheduling

Triggers may include:

```text
One-time date/time
Recurring schedule
Business-day schedule
Manual
External event
Condition
```

Use durable scheduler.

---

# 20. Recurrence

Support:

```text
Daily
Weekly
Monthly
Business days
Custom recurrence
```

Store timezone.

Handle daylight-saving/international cases even if launch market does not use DST.

---

# 21. Example — Weekly Prospecting

```text
Trigger: Monday 06:00 Africa/Lome

1. Load active ICP
2. Discover candidates
3. Deduplicate
4. Research
5. Qualify
6. Select top 10
7. Prepare outreach
8. Notify user
9. Wait for approval if send requested
```

Research can be A4.

Sending may remain A2.

---

# 22. Example — Morning Brief

```text
Trigger: business days 07:30

1. Calendar
2. Important emails
3. Open tasks
4. Commitments
5. Prospecting updates
6. Generate concise brief
7. Deliver
```

If one source fails, continue with partial result and disclose.

---

# 23. Event-Driven Workflows

Examples:

```text
New important email
Prospect replied
Calendar event created
Document uploaded
CRM opportunity changed
```

Use trusted integration events/webhooks.

Validate signatures.

Deduplicate events.

---

# 24. Event Idempotency

Providers retry webhooks.

Store event IDs.

```text
Event received
→ already processed?
  yes → acknowledge
  no → process
```

Prevent duplicate side effects.

---

# 25. Condition-Based Workflows

Example:

> “Quand un prospect répond positivement, prépare-moi une proposition de rendez-vous.”

Condition:

```text
New reply
AND classification=positive
AND confidence >= threshold
```

For uncertain classification, route to review.

---

# 26. Planning

Planning may be:

```text
Static workflow
Dynamic bounded plan
Hybrid
```

Prefer static/reusable workflows for repeated business processes.

Use dynamic planning for novel tasks.

Dynamic plans must still map to approved Skills.

---

# 27. Plan Representation

Conceptual:

```yaml
goal: string
steps:
  - id: s1
    skill: prospect.discover
    inputs: {}
  - id: s2
    skill: prospect.qualify
    depends_on: [s1]
```

Plans should be inspectable.

Do not store hidden chain-of-thought.

---

# 28. Plan Validation

Before execution:

- skill exists;
- permissions;
- input schemas;
- dependency graph;
- budgets;
- risk;
- impossible cycles;
- external-agent boundaries.

Reject invalid plans.

---

# 29. Skill Registry

All executable Skills registered with metadata:

```text
name
version
description
input schema
output schema
risk level
side effects
required permissions
cost class
timeout
provider
```

Planner chooses only registered Skills.

---

# 30. Tool Gateway

Execution path:

```text
Planner
→ Skill
→ Tool Gateway
→ Provider Adapter / MCP / Agent Zero / API / CLI
→ Verification
```

No direct arbitrary tool invocation from model.

---

# 31. Agent Zero Delegation

Agent Zero can be a bounded sub-agent.

Example step:

```yaml
skill: agent.delegate
objective: "Research these 5 companies"
allowed_tools:
  - web_search
  - browser_read
budget:
  max_minutes: 10
  max_cost: ...
output_schema: ProspectResearch[]
```

Agent Zero cannot expand permissions.

---

# 32. MCP Delegation

MCP servers expose capabilities.

Workflow sees normalized Skills.

Example:

```text
MCP Gmail
→ email.search

MCP Office
→ document.create
```

Do not couple workflow definitions to raw MCP transport details.

---

# 33. CLI Execution

For OfficeCLI or similar:

```text
Skill
→ sandboxed adapter
→ allowlisted command
→ timeout
→ resource limits
→ output validation
```

Never:

```text
LLM generates arbitrary shell
→ production server executes it
```

---

# 34. Budgets

Every autonomous workflow may define:

```text
max runtime
max model tokens
max provider spend
max tool calls
max records
max outbound actions
```

When exceeded:

```text
PAUSE
→ notify user
```

Do not silently exceed.

---

# 35. Cost Estimation

Before expensive runs, estimate where possible.

Example:

> “Cette recherche approfondie sur 500 entreprises peut utiliser des services payants. Le workflow est limité à 20 $.”

User can configure.

---

# 36. Rate Limits

Apply:

```text
per tenant
per user
per skill
per provider
per campaign
```

Use queues/backpressure.

---

# 37. Concurrency

Avoid conflicting workflows.

Example:

Two workflows both editing same document.

Use:

- locks;
- optimistic concurrency;
- version checks.

---

# 38. Workflow Versioning

When workflow definition changes:

Existing run should continue using version it started with unless explicit migration.

Store:

```text
workflow_version
```

Do not mutate active execution semantics unexpectedly.

---

# 39. Retry Policy

Per step:

```text
max attempts
backoff
retryable errors
non-retryable errors
```

Example:

429 → retry.

Invalid recipient → no blind retry.

---

# 40. Unknown Outcome

Most dangerous retry case:

```text
Send request timed out.
Did provider send?
```

State:

```text
UNKNOWN
→ verify provider state
→ only retry if safe
```

Avoid duplicate emails/payments/events.

---

# 41. Compensation

Some workflows need rollback/compensation.

Example:

```text
Create temporary file
→ later workflow fails
→ remove temporary file if safe
```

Not all actions are reversible.

Model compensation explicitly.

---

# 42. Partial Success

A workflow can complete partially.

Example:

```text
10 prospects requested
8 researched successfully
2 source failures
```

Status:

```text
PARTIAL_SUCCESS
```

Return exact result.

---

# 43. Cancellation

User can cancel:

> “Arrête cette tâche.”

Flow:

```text
Mark cancellation requested
→ stop cancellable steps
→ cancel external jobs if possible
→ prevent future side effects
→ preserve completed work
→ report state
```

---

# 44. Pause / Resume

Recurring workflows should support:

```text
Pause
Resume
```

Example:

> “Mets la prospection automatique en pause jusqu'au mois prochain.”

No data loss.

---

# 45. Kill Switch

Global:

```text
Pause All Autonomous Actions
```

Must stop:

- scheduled runs;
- queued side effects;
- recurring outreach;

as safely/quickly as possible.

Read-only user requests may remain available.

---

# 46. Notifications

Notify on:

```text
Approval needed
Task completed
Task failed
Budget exceeded
Important result
Recurring summary
```

Avoid notifying every internal step.

---

# 47. Notification Channels

Potential:

```text
In-app
Email
Push
WhatsApp Business where appropriate
```

User configures.

Do not expose sensitive content in lock-screen notifications by default.

---

# 48. Progress

For long tasks:

```text
12/50 prospects researched
```

or semantic stages:

```text
Discovery complete
Qualification in progress
```

Progress must reflect actual state.

---

# 49. User Interruption

User may change instructions during run.

Example:

> “Seulement les entreprises au Togo.”

System:

```text
Determine affected future steps
→ update run constraints if safe
→ invalidate stale planned actions
→ re-plan bounded remainder
```

Do not retroactively alter already-completed side effects.

---

# 50. Workflow Memory

Workflow state is not semantic memory.

Store execution state in workflow/task store.

Memory may store meaningful outcome:

> “User prefers prospect lists limited to Togo.”

Only if appropriate.

---

# 51. Workflow Learning

After repeated corrections, EMEFA may propose changing workflow.

Example:

> “Tu retires toujours les entreprises de moins de 20 employés. Veux-tu ajouter cette règle à ton workflow ?”

Require confirmation for strategic changes.

---

# 52. Templates

Provide reusable templates:

```text
Morning Brief
Weekly Prospecting
Meeting Preparation
Meeting Follow-Up
Inbox Triage
Weekly Report
Invoice Processing
Document Approval
```

Users customize.

---

# 53. Natural-Language Workflow Creation

User:

> “Chaque vendredi, prépare un résumé de la semaine et mets les tâches non terminées dans la semaine suivante.”

EMEFA should:

1. parse;
2. create draft workflow;
3. show interpretation;
4. ask only necessary clarification;
5. activate after confirmation if required.

---

# 54. Workflow Preview

Before activation show:

```text
Trigger
Actions
Data accessed
Side effects
Approvals
Limits
Notifications
```

User should understand what will happen.

---

# 55. Workflow Builder UX

Potential:

```text
When...
[Every Monday at 7:00]

Do...
[Find prospects]
[Qualify]
[Prepare messages]

Approval...
[Before sending]

Limits...
[10 prospects/week]
```

Natural language + visual editor.

---

# 56. Generated Workflows Must Be Validated

LLM-generated workflow definitions must pass schema/policy validation.

Never execute arbitrary generated JSON blindly.

---

# 57. Background Workers

Separate:

```text
API / Realtime Layer
from
Worker Execution
```

Workers should be horizontally scalable.

---

# 58. Queue Architecture

Use queues for:

- background tasks;
- provider calls;
- retries;
- scheduled work.

Select infrastructure after repository audit.

Avoid premature distributed complexity.

---

# 59. Task Leasing

Workers need safe ownership.

Pattern:

```text
claim/lease
→ execute
→ heartbeat
→ complete
```

If worker dies, task becomes recoverable.

---

# 60. Exactly-Once Illusion

True exactly-once across external systems is difficult.

Use:

```text
at-least-once processing
+
idempotency
+
verification
+
deduplication
```

Design explicitly.

---

# 61. Timeouts

Every external step requires timeout.

No indefinite hanging.

On timeout:

- classify;
- retry if safe;
- verify unknown outcomes;
- fail/partial if needed.

---

# 62. Heartbeats

Long-running external agents/tools should emit heartbeat/progress.

If heartbeat missing:

- detect stale;
- cancel/retry according to policy.

---

# 63. External Agent State

If Agent Zero runs remotely:

Store:

```text
external_job_id
provider
started_at
last_heartbeat
status
```

Do not rely only on open socket.

---

# 64. Security Context

Every workflow run carries:

```text
tenant_id
user_id
assistant_id
permissions snapshot/reference
correlation_id
```

Every Skill rechecks authorization at execution time.

Do not trust planner alone.

---

# 65. Credential Scope

Workers receive only credentials required for current Skill.

Do not give all tenant secrets to every workflow.

Use vault/token broker where possible.

---

# 66. Prompt Injection in Autonomous Work

Autonomy increases risk.

External content:

```text
email
website
document
MCP response
```

is untrusted data.

It cannot expand:

- permissions;
- budget;
- tools;
- workflow scope.

---

# 67. Exfiltration Prevention

Before sending/uploading data:

- destination allowed?
- user authorized?
- data sensitivity?
- workflow purpose?

Block suspicious transfers.

---

# 68. Approval Bypass Prevention

No external tool/agent can mark approval as granted.

Approval authority belongs to EMEFA policy system.

---

# 69. Audit Trail

For every run:

```text
Trigger
Inputs
Plan
Skills
Approvals
External calls
Artifacts
Results
Failures
Costs
```

Redact secrets.

---

# 70. Replay / Debugging

Support safe replay in test/staging.

Production replay of side-effecting steps requires safeguards.

Do not resend emails during debugging.

---

# 71. Dry Run

Workflows should support:

```text
DRY_RUN
```

Simulate plan and side effects.

Useful before enabling autonomy.

Example:

> “Montre-moi ce que cette automatisation ferait cette semaine sans rien envoyer.”

---

# 72. Sandbox Mode

New Skills/workflows can run against:

- mock providers;
- test accounts;
- sandbox files.

Required before production for high-risk integrations.

---

# 73. Workflow Testing

Tests:

```text
unit
integration
contract
end-to-end
failure injection
retry/idempotency
permission
tenant isolation
```

---

# 74. Failure Injection

Simulate:

- worker crash;
- DB unavailable;
- provider 429;
- timeout after send;
- webhook duplicate;
- approval expires;
- external agent hangs;
- user cancels mid-run.

Verify recovery.

---

# 75. Observability

Metrics:

```text
runs_started
runs_completed
runs_failed
partial_success
approval_wait_time
step_latency
retry_count
cost_per_run
cancel_rate
```

Trace by correlation ID.

---

# 76. Workflow Health

Dashboard:

```text
Active
Waiting for approval
Failed
Paused
Recurring
Budget alerts
```

For users and operators.

---

# 77. Stuck Run Detection

Detect runs with:

- no heartbeat;
- overdue wait;
- repeated retry;
- missing external callback.

Alert/recover.

---

# 78. SLA Classes

Potential:

```text
Interactive
Background
Batch
Low Priority
```

Voice tasks need fast priority.

Large prospect research can run background.

---

# 79. Resource Scheduling

Avoid background workflows starving realtime conversations.

Use separate queues/pools/priorities.

---

# 80. Multi-Tenant Fairness

Prevent one customer from consuming all workers/provider quota.

Use tenant-level concurrency quotas.

---

# 81. Example — Autonomous Administrative Day

Configured workflow:

```text
07:00 Morning Brief
08:00 Inbox Triage
Before Meetings: Prepare Brief
Throughout Day: Track Commitments
17:30 End-of-Day Summary
```

EMEFA works within permissions.

No need for user to initiate each action.

---

# 82. Example — Prospecting Autonomy

Policy:

```text
Research: A4
Qualification: A4
Draft outreach: A4
Send: A2
Max 10 prospects/week
Target: Togo
ICP: Hotels 20+ employees
```

Workflow runs.

Monday:

> “10 prospects sont prêts. 7 messages sont prêts pour validation.”

---

# 83. Example — Bounded Send Autonomy

Future policy:

```text
Send follow-up automatically
ONLY IF:
- recipient previously engaged
- approved campaign
- max 1 follow-up
- no opt-out
- no reply since last message
```

This is bounded A3/A4.

---

# 84. Example — Meeting Automation

Trigger:

```text
Calendar event starts in 24 hours
AND external attendees exist
```

Workflow:

```text
Retrieve context
→ prepare brief
→ notify user
```

No approval needed for read-only preparation if policy permits.

---

# 85. Example — Monthly Report

Trigger:

```text
Last business day 14:00
```

Workflow:

```text
Gather metrics
→ generate spreadsheet
→ generate executive report
→ validate
→ request approval
→ send
```

If approval not received, do not send.

---

# 86. Example — User Offline

User starts:

> “Analyse ces 100 entreprises.”

Then closes app.

Expected:

- task continues;
- state persists;
- budget enforced;
- result available later;
- notification on completion.

---

# 87. Example — Provider Failure

At step 4/7 provider fails.

Expected:

```text
retry if safe
→ fallback if policy allows
→ otherwise pause/fail
→ preserve first 3 steps
→ no duplicate side effects
```

---

# 88. Example — Cost Limit

Workflow budget:

```text
$5
```

At $4.90:

- do not start expensive next step if expected to exceed limit;
- pause;
- ask user to increase budget or reduce scope.

---

# 89. MVP Scope

## Must Have

- durable tasks;
- background workers;
- explicit run/step states;
- manual workflows;
- scheduled workflows;
- approvals;
- retries;
- idempotency;
- cancellation;
- budgets;
- notifications;
- audit.

## Next

- event-driven triggers;
- natural-language workflow builder;
- pause/resume;
- workflow templates;
- Agent Zero bounded delegation.

## Later

- sophisticated condition engine;
- workflow marketplace;
- optimization from outcomes;
- enterprise policy engine.

---

# 90. Workflow Marketplace Future

Users may install:

```text
Weekly Prospecting
Invoice Processing
Meeting Follow-Up
Social Content Preparation
Customer Support Triage
```

A workflow package declares:

- required Skills;
- permissions;
- configuration;
- triggers;
- costs.

Never install with hidden permissions.

---

# 91. Skills Marketplace Relationship

Skills are capabilities.

Workflows combine capabilities.

Example:

```text
Skills:
email.send
calendar.create
document.generate

Workflow:
Client Onboarding
```

Keep marketplace concepts distinct.

---

# 92. Definition of Done — Autonomous Workflow

A production autonomous workflow requires:

- versioned definition;
- durable run state;
- typed steps;
- permission checks;
- autonomy level;
- approval checkpoints;
- budgets;
- timeouts;
- retry policy;
- idempotency;
- cancellation;
- verification;
- audit;
- observability;
- tests;
- rollback/compensation where relevant.

---

# 93. Anti-Patterns

Never build:

```text
while not done:
    ask LLM what to do
    execute anything it says
```

Never:

- run long tasks in request thread;
- store workflow only in model conversation;
- let external agent expand scope;
- retry unknown side effects blindly;
- allow hidden recurring automation;
- let schedules ignore timezone;
- lose tasks when user disconnects;
- treat “no exception” as verified success;
- hide costs;
- make autonomy all-or-nothing.

---

# 94. North-Star Interaction

User:

> “EMEFA, à partir de maintenant, chaque semaine trouve-moi dix prospects sérieux au Togo. Prépare les messages, mais demande-moi avant d'envoyer.”

EMEFA translates this into:

```text
Workflow: Weekly Prospecting
Trigger: Weekly
Target: 10 qualified prospects
Geography: Togo
Discovery: A4
Research: A4
Qualification: A4
Drafting: A4
Sending: A2
Budget: configured
Suppression: active
Notification: when ready
```

Then every week:

```text
runs in background
→ survives disconnects
→ finds prospects
→ verifies/qualifies
→ prepares messages
→ waits at approval checkpoint
```

The user sees:

> “Cette semaine, 10 prospects sont prêts. J'ai préparé 8 messages personnalisés. Rien n'a été envoyé sans ton accord.”

That is trustworthy autonomy.

---

# 95. Final Principle

> **EMEFA should be autonomous enough to save real work, but constrained enough to remain trustworthy.**

The architecture must make this equation true:

```text
Autonomy
=
Durable Execution
+ Explicit Permissions
+ Bounded Scope
+ Budgets
+ Verification
+ Human Control
```

The product becomes transformative when the user can delegate an outcome, close the application, return later, and find that EMEFA has done the work correctly — with a clear record of what happened and without crossing the boundaries the user established.
