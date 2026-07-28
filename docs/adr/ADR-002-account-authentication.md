# ADR-002 — Account authentication and identification

> **Status:** Accepted · **Date:** 2026-07-28 · **Supersedes part of:** ADR-001 §3

## Context

ADR-001 deliberately deferred real accounts: devices enrolled with a shared activation
code were the only credential, and it named "a second real user, or any external pilot"
as the revisit condition. The current work adopts capabilities from `jarvis-OS`, and the
user asked explicitly for its "système d'authentification / identification".

The audit (`docs/JARVIS_OS_GAP_ANALYSIS.md` §1.6) found that jarvis-OS authenticates with
a **single static bearer token** read from `.env`, injected into the served HTML, with
`/admin`, `/dashboard` and **all WebSocket upgrades** exempt from the check. That is
coherent for a `127.0.0.1` desktop app and incoherent for a browser-reachable product.
Adopting it would remove EMEFA's hashed per-device tokens, secure cookies, rate-limited
enrolment, revocation and audit trail.

What EMEFA genuinely lacks is not a stronger transport credential — it is an **identity**
behind the device. Today `usr_default` is a constant; nothing distinguishes two humans
sharing an instance, and no resource can be scoped to a person.

## Decision

1. **Reject the jarvis-OS authentication model.** Static shared bearer tokens, HTML-embedded
   credentials and blanket WebSocket exemptions are not adopted, in whole or in part.
2. **Introduce real accounts.** A `accounts` table under the existing
   `tenant → user → assistant` hierarchy: e-mail, password hash, status, role, timestamps.
   Passwords are hashed with a memory-hard KDF (scrypt from the standard library, with
   per-account salt and recorded parameters so the cost can be raised later without
   invalidating stored hashes).
3. **Devices become sessions owned by an account.** The existing device row gains an
   account binding. The enrolment code remains as *instance bootstrap only*: it authorises
   creating the **first** owner account, then stops being an authentication path.
4. **Sessions carry the identity.** The session cookie continues to be the transport
   (`httponly`, `secure`, `samesite=strict`); resolving it now yields an authenticated
   *principal* — account + tenant + assistant — and every repository call is scoped by it.
   Client-supplied identity is never trusted (CLAUDE.md §40).
5. **Identification is cryptographic; recognition is presentational.** The "who woke me"
   greeting is driven by the authenticated principal, not by biometrics. Face matching is
   explicitly out of scope here; if added later it is a client-side convenience unlock over
   an existing session, never a primary credential, and requires its own ADR.
6. **Backward compatibility.** Existing enrolled devices keep working: the migration binds
   them to the seeded owner account. No user is logged out by the upgrade.

## Alternatives considered

- **Port jarvis-OS's bearer-token guard.** Rejected: a strict security regression against
  what EMEFA already ships, for zero capability gained.
- **Full OIDC / external identity provider now.** Rejected for this slice: it adds an
  external dependency and an operational surface before there is a second tenant. The
  account table is shaped so an external subject identifier can be added later.
- **Keep enrolment codes as the only credential.** Rejected: it is a shared secret with no
  identity, so nothing downstream — memory, initiatives, audit — can name a person.

## Consequences

- Memory, initiatives, missions, tasks and audit entries gain a real owner, which is the
  precondition for everything in the proactive slice.
- The activation flow gains one step (create the owner account) the first time an instance
  is opened.
- Password reset is *not* implemented in this slice; recovery is instance-operator level
  (documented in `docs/SECURITY.md`). This is a stated limitation, not an oversight.

## Revisit conditions

A second tenant, an external pilot, SSO demand, or any requirement for delegated access
(an assistant acting for several colleagues) triggers a follow-up ADR on organisation
membership and role granularity.
