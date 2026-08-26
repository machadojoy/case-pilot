# Model: Membership (who works at which firm)

> Status: **designed 2026-08-26, not built.** Central question locked by DESIGN.md §10 Q5.
> See `../../DESIGN.md` §3 (identity, and the Teams direction) and `../schema.md`.

## Purpose

Links a `User` to an `Organization` with a **role**. It is the **insider** edge: having a
row here means you work at the firm and can see its book of business.

A role is contextual to a workspace, so it lives here rather than on `User` — the same
person can be a `lawyer` at one firm and an `admin` at another.

## Fields (decided)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK. **UUID everywhere.** |
| `user_id` | UUID | FK → `users.id`. **Never `ON DELETE CASCADE`** (see *Erasure*). |
| `org_id` | UUID | FK → `organizations.id`. |
| `role` | str + CHECK | `owner` \| `admin` \| `lawyer` \| `staff`. |
| `created_at` / `updated_at` | datetime (tz-aware) | Convention: both on every table. |

**Unique on `(user_id, org_id)`** — one role per person per firm.

Nothing else. No `invited_by`, no `status`, no `joined_at` (that is `created_at`).

### `role` gets the same treatment as `User.status`

`str` + a CHECK constraint generated from a `StrEnum`, **not** a Postgres `ENUM` type —
and the reasoning is stronger here, because roles churn more than statuses:

```python
CheckConstraint(
    "role IN ({})".format(", ".join(f"'{r}'" for r in Role)),
    name="ck_memberships_role",
)
```

Postgres has no `ALTER TYPE ... DROP VALUE`. `table=True` disables Pydantic validation, so
the CHECK is the **only** enforcement. **Alembic autogenerate cannot see CHECK constraint
changes** — hand-write that migration, and prove it with `\d memberships`, because the test
suite builds its schema with `create_all` and will not notice a missing constraint.

### `customer` is not a role

Locked by Q5. The customer relationship is carried by `Dossier.customer_user_id`. Insider
and outsider are different *authorization shapes*, not permission levels:

| | scope predicate |
|---|---|
| insider (has a `Membership`) | `WHERE org_id = :org` |
| outsider (has a `Dossier`) | `WHERE org_id = :org AND customer_user_id = :me` |

The absence of a `Membership` row **is** the guarantee that someone cannot get org-wide
scope. A firm's own employee can also be its client — one `Membership`, one `Dossier`,
no conflict.

## Scope of the first slice

Rows are created **only by the organization-creation flow**, granting the creator `owner`.

No invitations, no member list, no removal endpoint. A firm is a one-person workspace for
now. Adding a second person needs an `Invitation` entity (token, expiry — the invitee
usually has no `User` row yet) and a mailer, which the auth slice already cut for lack of
one. That is its own slice.

Small as it is, this buys three things immediately:

1. org creation grants its creator ownership (DESIGN.md: creation is transactional —
   `Organization` + `User` + `Membership(owner)`, all-or-nothing);
2. `POST /organizations` becomes authorizable;
3. `GET /organizations` gets scoped to firms you belong to — **closing a live leak**,
   since today it returns every firm in the system to anyone.

## Rules to enforce when the endpoints exist

None of these can be violated by the first slice — there is no removal, role-change or
erasure endpoint — so they are recorded now and enforced when each lands.

- **At least one `owner` per organization.** An org with zero owners is orphaned and
  unadministrable. This is a cross-row constraint: **Postgres does not guarantee it** and a
  simple `CHECK` cannot express it. Enforce in the service, and do not let a future reader
  assume the database has it covered. A firm may have several owners (co-founders), which
  is why the invariant is *at least* one.
- **No self-role-change.** An `admin` promoting themselves to `owner` is privilege
  escalation.
- **Revocation is a hard `DELETE`, never a tombstone.** This is the deliberate
  counter-example to `User`'s erasure (`user.md`): a tombstoned membership would occupy the
  `(user_id, org_id)` unique slot forever and block re-adding someone who once left. If the
  firm wants history, that is an audit log — a different table with different retention.

## Erasure: memberships go, case files stay

Erasing a `User` **deletes their memberships**. A tombstone holding a live membership is a
ghost employee with access.

This looks like it violates DESIGN.md §2a's "never cascade from `users` to tenant data",
and it does not — the distinction is worth stating because it will look wrong otherwise:

| | what it is | on erasure |
|---|---|---|
| `Membership` | an **access grant** | deleted — nobody is obliged to retain it |
| `Dossier` | a **legal record**, retention governed by the firm | survives |

Grants go, records stay. The FK still must not be `ON DELETE CASCADE`: the deletion is a
deliberate step in the erasure routine, not a side effect of touching the `users` row.

## Teams do not change this table

DESIGN.md §3 records `Team` / `TeamMembership` as the decided direction, built with
`Dossier`. It is a **second axis**, not a replacement — a team lead is
`Membership(role=lawyer)` **+** `TeamMembership(role=lead)`.

So: do not add `lead` to this role enum, and do not drop the `(user_id, org_id)` unique
constraint in anticipation. Both stay correct under the team model.

## Deliberately NOT included yet (YAGNI)

- **`Invitation`** — and with it invite/list/remove endpoints. Needs a mailer.
- **`status`** (`invited` / `active`) — only meaningful once invitations exist.
- **`invited_by`** — audit, not access control.
- **Role-change endpoint** — with it, the self-escalation rule above.
- **Audit log of role changes** — a separate table when a firm needs the history.

## To resolve when we build

- The org-creation flow currently creates only the `Organization`. It has to become
  `Organization` + `Membership(owner)` in one transaction — the router owns the boundary,
  the services stage only.
- Which authorization dependency shape to use for "is a member of / has role in" — likely
  a FastAPI dependency taking the org id from the path.
