# ADR-003 — Per-tenant connected accounts, encrypted at rest

> **Status:** Accepted · **Date:** 2026-07-28 · **Scope:** credential storage and mailbox
> resolution. **Not** full multi-tenancy — see §"What this does not do".

## Context

The target model given was:

```text
Tenant A · Jean  · jean@gmail.com  · encrypted token
Tenant B · Amina · amina@gmail.com · encrypted token
```

The code did not support it. The mailbox was a single instance-wide
`HimalayaEmailProvider` built from `EMEFA_EMAIL_ACCOUNT` and shared by every device, and
`Device` did not even carry its owner, so nothing in a request could say *whose* data was
being touched. ADR-001 had reserved the `tenant → user → assistant` shape and every table
carries the columns, but no resource was actually resolved through them.

Storing third-party OAuth tokens raises the stakes: a leaked or mis-scoped token is access to
someone's real mailbox, not a row in our database.

## Decision

**1. Connected accounts are a first-class, scoped resource.** One row per
`(tenant_id, user_id, provider)`, enforced by a unique index. "Jean's Gmail" and "Amina's
Gmail" are structurally distinct rows that no query can conflate.

**2. Every vault operation requires an `AccountScope`.** There is no method that returns a
credential without one, and the scope always lands in the `WHERE` clause. Isolation cannot be
forgotten at a call site because there is no call shape that omits it.

**3. The scope is bound into the ciphertext.** Secrets are encrypted with AES-256-GCM, using
`tenant|user|provider` as the AEAD *associated data*. A ciphertext lifted out of Amina's row
and written into Jean's row **fails to decrypt**. This is the important decision: it converts
a SQL mistake, a bad restore or a tampered database from a silent cross-tenant read into a
loud, tested error. A `WHERE` clause alone would not.

**4. The vault fails closed.** With no `EMEFA_SECRET_KEY` it refuses to store a secret — HTTP
503 with an explanatory detail — rather than degrading to plaintext. An unreadable credential
returns nothing and never falls through to another mailbox.

**5. The scope is derived server-side from the authenticated device.** `Device` now carries
`user_id` and `tenant_id` (joined from `users`), and the API has **no tenant or user field at
all**. There is nothing to spoof, which is stronger than validating a field a client sends
(§40).

**6. Secrets are write-only across every surface.** No endpoint echoes a token; the audit log
records the provider and the account label (an identifier, not a secret) and never the token.

**7. The legacy instance mailbox belongs to the default owner only.** The pre-existing
single-mailbox deployment keeps working unchanged, but another tenant can never inherit it.

## Alternatives considered

- **A `WHERE tenant_id = ?` clause and nothing more.** Rejected as insufficient on its own:
  it protects against honest queries, not against the failure modes that actually leak data
  (a restore from another environment, a migration bug, a manual fix). Scope-bound ciphertext
  costs nothing extra and is testable.
- **A separate database per tenant.** Rejected for now: it solves isolation by multiplying
  operational surface — migrations, backups, connections — well before there is a second real
  tenant. Revisit at genuine platformization; the scoped-vault interface does not prevent it.
- **A dedicated secrets manager (Vault, AWS/GCP KMS).** Deferred, not rejected. It is the
  right answer at scale, and `key_version` exists so the stored key can be rotated or
  externalised. Adopting one now would add infrastructure the single-node deployment does not
  have.
- **Encrypting the whole database file (SQLCipher).** Rejected as an alternative, reasonable
  as a complement: file-level encryption protects a stolen disk but gives no per-tenant
  binding, so a cross-tenant row copy would still decrypt fine.
- **Deriving a distinct key per tenant.** Considered and deferred. AAD binding already
  achieves the isolation property; per-tenant keys mainly add value alongside an external KMS,
  and would complicate rotation before it is needed.

## What this does **not** do

Stated plainly, because the gap is easy to misread as closed:

- ~~**The rest of the data is still single-scope.**~~ **Closed (2026-07-29).** CRM, tasks,
  memory and agenda are now scoped through `domain/scope.ScopedStore`, and requests resolve a
  per-owner `Workspace` (including the agent's tool shelf). Meetings, prospects, routines,
  documents, profiles and reports remain single-scope — tracked as an executable list in
  `tests/test_tenant_isolation.py`, which fails when a new tenant table is added unscoped.
- **There is no OAuth flow and no Gmail adapter.** Tokens can be stored, listed, revoked and
  decrypted by their owner; `MailboxResolver.build_provider` is the seam a real adapter plugs
  into. Until it ships, a connected account resolves to *no* provider and says so, rather than
  pretending to work.
- **Enrollment is still one shared instance code.** A new device joins the default user; the
  second tenant in the tests exists because rows were inserted directly. Real tenant
  onboarding needs account authentication, which is a separate decision.

## Consequences

**Positive.** The credential model the specification describes now exists and is enforced by
tests that assert the hard property (cross-tenant ciphertext refuses to decrypt), not just
the easy one. The device→owner→resource chain is established and can be reused to scope the
remaining repositories. Nothing about the current single-user deployment changes.

**Costs.** A new runtime dependency (`cryptography`, PyCA — the reference implementation,
Apache/BSD). One more secret to manage in deployment: losing `EMEFA_SECRET_KEY` makes stored
tokens unrecoverable, which is the intended trade and must be in the runbook. Key rotation is
possible in principle (`key_version`) but no re-encryption tooling exists yet.

## Revisit when

- The remaining repositories are scoped by tenant → the isolation tests here become the
  template, and a shared `Scope` type should replace the per-module defaults.
- A real OAuth adapter ships → refresh-token rotation, expiry handling and re-consent.
- A second tenant is genuinely onboarded → account authentication, and per-tenant key
  derivation with an external KMS.
