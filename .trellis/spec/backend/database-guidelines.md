# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

(To be filled by the team)

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)

## Scenario: One Active Primary Workspace Per User

### 1. Scope / Trigger

- Trigger: creating, reactivating, or changing a `sys_tenant_user` membership, transferring workspace ownership, or repairing historical primary-workspace flags.

### 2. Signatures

- Application switch: `assign_user_to_tenant(..., is_primary=True)` delegates to the shared primary-membership switch in `apps.system.crud.tenant`.
- Database invariant: unique `sys_tenant_user(user_id)` where `status = 1 AND is_primary = true`.
- Index name: `uq_sys_tenant_user_active_primary`.

### 3. Contracts

- `is_primary` is the user's default workspace; it does not mean workspace owner or important member.
- A user may have many active memberships, but at most one active membership may have `is_primary=true`.
- Setting a target membership primary must lock the user and membership rows, clear all other primary flags, flush, and then set the active target primary in the same transaction.
- `is_primary=false` means that the operation does not switch the user's default workspace; it must not clear an existing primary membership.
- Historical repair may clear duplicate flags but must not delete workspaces, memberships, roles, or administrator-created data.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Target membership is active | Atomically make it the sole active primary membership |
| Target membership is missing or inactive | Reject the primary switch |
| An inactive membership retains a stale primary flag | Clear the stale flag before reactivation, then apply the requested switch behavior |
| Ordinary membership update passes `is_primary=false` | Preserve the existing active primary workspace |
| Concurrent paths attempt different active primaries | User-row locking serializes the switch; the partial unique index is the final guard |
| Migration finds duplicate active primaries | Keep one deterministic winner, clear only the other primary flags, then create the index |

### 5. Good/Base/Bad Cases

- Good: assigning workspace B as primary clears workspace A before setting B, all inside one transaction.
- Base: adding workspace B as a non-primary membership leaves workspace A primary.
- Bad: directly setting `membership.is_primary = True`, or treating every owned workspace as primary.

### 6. Tests Required

- Service tests must cover sequential primary switches, non-primary updates, reactivation of stale inactive primary flags, sample-workspace initialization, and ownership transfer.
- Migration tests must execute the duplicate repair and index creation, assert the deterministic winner, and prove that a second active primary for one user is rejected.
- Tests must also prove that different users may each have a primary membership and that inactive primary flags are outside the partial index.

### 7. Wrong vs Correct

#### Wrong

```python
membership.is_primary = bool(is_primary or membership.is_primary)
```

#### Correct

```python
if is_primary:
    membership = _set_primary_tenant_membership(session, membership)
```
