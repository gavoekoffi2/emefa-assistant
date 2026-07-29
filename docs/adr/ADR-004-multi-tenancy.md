# ADR-004 — Multi-tenancy: scope belongs to the store, not the query author

**Status:** accepted · **Date:** 2026-07-29 · **Supersedes the scope limit recorded in ADR-003**

## Context

ADR-001 defined a tenant/user/assistant hierarchy but ran the product in
single-tenant mode: fixed `ten_default` / `usr_default` identifiers, one shared
enrollment code, and no filtering anywhere. ADR-003 isolated connected-account
credentials cryptographically and recorded honestly that **everything else was
still single-scope**.

Selling EMEFA to more than one company requires closing that gap. The
requirement was stated more precisely than "add tenant filters":

> Je ne veux plus dépendre du développeur pour penser à ajouter un filtre tenant.
> L'architecture doit rendre impossible, ou extrêmement difficile, l'écriture
> d'une requête non cloisonnée.

That rules out the obvious approach. Adding `AND tenant_id = ?` to every query is
correct exactly until someone forgets, and a forgotten predicate fails **open**
and **silently** — the worst possible failure shape for this class of bug.

A second constraint shaped the data model: resources that belong to the company
must not be attached to individuals. A CRM filtered by `user_id` would give each
colleague a private client list, which is not what a company means by "our
clients".

## Decision

### 1. The scope is applied by the store

Every repository inherits `ScopedStore`. No method on it accepts a query without
a scope; the predicate is composed by the store and placed at the head of the
`WHERE` clause. There is no method signature through which an unscoped read can
be expressed, so scoping is not a rule to follow but a property of the interface.

`insert()` stamps `tenant_id`, `user_id`, `created_by_user_id` and
`updated_by_user_id`. `update_scoped()` and `delete_scoped()` carry the scope in
the key, so a write aimed at another company's row reports "not found" rather
than applying.

### 2. Ownership is declared per repository, not per query

```python
class CrmRepository(ScopedStore):
    ownership = Ownership.TENANT   # shared by every colleague

class MemoryRepository(ScopedStore):
    ownership = Ownership.USER     # personal to one person
```

`TENANT` filters on `tenant_id`; `USER` filters on `tenant_id AND user_id`. The
decision is made once, where the data model is defined, and cannot drift between
two queries against the same table.

Company-owned resources still record *who* created and last touched them, and
tasks carry an assignee — attribution without fragmentation.

### 3. The scope comes from the authenticated device, never from the request

```
Cookie/Bearer → device → users.tenant_id → Scope → Workspace → bound repositories
```

Nothing in the request body, query string or headers influences the scope. A
`Workspace` binds every repository — and the agent tool shelf built on them — to
one scope, memoised per scope.

### 4. Uniqueness constraints include the tenant

Scoping reads says nothing about constraints. A `UNIQUE` key that omits
`tenant_id` is a shared resource between companies regardless of how correct
every `WHERE` clause is. Constraints therefore carry the tenant, and a
conformance test walks the schema to enforce it.

### 5. Authorisation is a global default-deny dependency

The same argument applies to permissions: a per-route check is a rule to
remember. One global dependency covers every route, and a route with no policy
is refused rather than allowed.

### 6. Identity tables are exempt, bounded, and pinned by test

`tenants`, `users`, `auth_tokens` and `invitations` bypass `ScopedStore` because
they are read *before* the caller's tenant is known — scoping them would be
circular. The exemption is bounded: every lookup key is a high-entropy secret or
an already-proven id, no method accepts a browsable criterion, and administrative
reads take the tenant as a required argument. A test asserts the exemption is
exactly those four names.

## Alternatives considered

**Per-tenant database file.** Strongest isolation, and attractive with SQLite.
Rejected for now: it moves the problem to connection routing, complicates
migrations across N files, and makes future cross-tenant operational queries
(billing, support, usage) hard. Revisit if tenant count or the concurrent-write
limit forces it — the `Scope` boundary is where that change would land, and
nothing above it would need to move.

**PostgreSQL row-level security.** The textbook answer, and genuinely stronger:
the database enforces the predicate rather than the application. Rejected *for
this step* because migrating the database engine and closing the isolation gap at
the same time would make a regression in either impossible to attribute. The
`ScopedStore` boundary is deliberately shaped so RLS could sit behind it later.

**Adding `AND tenant_id = ?` to every query.** Rejected as stated above.

**Filtering everything by `user_id`.** Rejected: it contradicts what a company
means by shared data, and I had started down this path before correcting it.

## Consequences

**Good.** Unscoped queries are not expressible through the repository interface.
Ownership is declared once per table. New tables are caught by a conformance test
rather than by review. New routes are default-denied. Three real defects were
found by these tests, none by reading code.

**Costs.** Every repository must inherit `ScopedStore`; raw `storage.connect()`
in domain code is now a smell requiring justification. A workspace is memoised
per scope, so many tenants means many tool shelves in memory — bounded today,
worth measuring later. `ProfileRepository` provisions on demand, adding a write
to a first read.

**Accepted risks.** Isolation is enforced by the application, not the database:
anyone with direct file access or writing raw SQL bypasses it. Connected-account
secrets are additionally bound cryptographically (ADR-003) so the highest-value
data fails loudly on a boundary violation, but business data does not have that
property. Database-at-rest encryption, per-tenant backup and company deletion are
not built; they are listed with their risks in `docs/MULTI_TENANCY_AUDIT.md` §7.

## Revisit when

- tenant count or write concurrency strains a single SQLite file;
- a compliance requirement demands database-enforced isolation → PostgreSQL RLS;
- a customer requires physical data separation → per-tenant database;
- cross-tenant operations (billing, support tooling) need a deliberate, audited
  way through the boundary rather than an exception to it.

## References

- `backend/emefa/domain/scope.py`, `backend/emefa/domain/accounts.py`
- `backend/emefa/api/workspace.py`, `backend/emefa/api/authorization.py`
- `docs/MULTI_TENANCY_AUDIT.md` — full table-by-table audit
- `backend/tests/test_tenant_isolation.py`, `test_two_companies.py`, `test_permissions.py`
