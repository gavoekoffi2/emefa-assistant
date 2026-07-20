# ADR-001 — Identity and Tenancy Model (foundation definition)

> **Status:** Accepted · **Date:** 2026-07-20 · **Phase:** 1 (Foundation Stabilization)

## Context

The current implementation authenticates *devices* (browser/phone enrolled with a shared
activation code) and nothing else. There is no user, organization, or assistant entity, so
upcoming capabilities (onboarding, memory, skills, workflows, audit) have no owner to attach
to. The specs require a tenant-ready architecture (`CLAUDE.md` §31, roadmap §14) while the
shipped product is deliberately a private single-user instance. Introducing full multi-tenant
auth now would be speculative complexity (roadmap §83 defers platformization).

## Decision

1. **Canonical identity hierarchy** (to be used by every future persistent entity):
   `tenant_id → user_id → assistant_id`, with devices belonging to a user.
2. **Single-tenant instance mode for the MVP:** one implicit tenant, one implicit user, one
   assistant. Implicit rows are created by migration when the first consumer needs them
   (Phase 2 onboarding), not before. Their IDs are constants resolved server-side — never
   trusted from the client.
3. **Devices remain the authentication mechanism** for the private instance; a device row
   will gain a `user_id` column via migration when the user entity lands. Enrollment-code
   authentication is acceptable only for single-tenant mode and will be replaced by real
   account auth at platformization (future ADR).
4. **Schema changes go through the numbered migration list** now implemented in
   `DeviceRepository` (`MIGRATIONS` tuple + `schema_migrations` table). No ad-hoc DDL.
5. **Tenant scoping discipline starts now:** every new table added from Phase 2 onward must
   carry its owning scope column(s) from day one, even while values are constant.

## Alternatives considered

- **Full user/org/auth system now** — rejected: no product need yet; high risk of building
  the wrong shape before onboarding requirements exist.
- **Stay device-only with no defined hierarchy** — rejected: Phase 2+ entities would attach
  to devices, which are revocable transport credentials, not identities; retrofitting owners
  later is the expensive path.

## Consequences

- Phase 2 (assistant identity & onboarding) has a defined place to persist data.
- Cross-tenant isolation tests become meaningful once real tenancy activates; until then the
  invariant is "no query without an owning scope" enforced by review.
- The enrollment-code model is explicitly documented as a single-tenant simplification.

## Revisit conditions

Platformization (roadmap Phase 12), a second real user, or any external pilot requiring
per-user data separation triggers the follow-up ADR on account authentication and real
tenant rows.
