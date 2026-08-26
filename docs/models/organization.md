# Model: Organization (the tenant / workspace)

> Status: **core locked (2026-08-13).** See `../../DESIGN.md` for the big picture.

## Purpose

The **tenant root**. One row per law-firm workspace. Every tenant-scoped table carries its
`org_id`. Created when a firm signs up; the first user becomes its `owner` (via `Membership`).

## Fields (decided)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK. **UUID everywhere** — non-enumerable, URL-safe, avoids an int→UUID migration later. |
| `name` | str | display name, e.g. "XYZ Family Law". Mutable. |
| `slug` | str | **unique** URL/workspace handle, e.g. `xyz-family-law`. Auto-generated from `name` at creation; **stable** (renaming `name` does not change it). |
| `created_at` | datetime (tz-aware) | server default `now()`. |
| `updated_at` | datetime (tz-aware) | auto-updates on change. **Convention: both timestamps on every table.** |

## Deliberately NOT included yet (YAGNI)

- `status` / suspended — add with a real suspension flow.
- `plan` / billing tier — Phase 5.
- `settings` / triage policy — its own entity later.
- `owner_id` — **derive** from `Membership(role=owner)`; don't duplicate identity here.

## Creation is transactional (behavior, not a field)

Signing up a firm creates — atomically — the `Organization` **+** the owner `User` **+** a
`Membership(role=owner)`. All-or-nothing.

## Endpoints — and the two that are deliberately missing

Built (2026-08-19), under `/api/v1`:

```
POST /organizations          201
GET  /organizations          paginated
GET  /organizations/{id}     200 / 404
```

**There is no `PATCH` and no `DELETE`, on purpose.** Recorded 2026-08-26 so the gap
doesn't read as an oversight.

### `PATCH` — waiting on authorization, not design

Only `name` is mutable; `slug` is the stable handle and renaming it breaks every existing
link (see below). So `PATCH` is a one-field endpoint, and what it actually needs is an
answer to *"who may rename this firm?"* — `owner`/`admin` only, which is a `Membership`
query. Shipping it before `Membership` would let anyone on the internet rename anyone's
firm: strictly worse than today, where they can only create and read.

Ship it with the slice that fixes the two existing endpoints (`POST` is unauthenticated;
`GET` lists every firm in the system to everyone).

### `DELETE` — not a Phase 1 feature at all

Deleting an `Organization` means deleting a **tenant**: its `Dossier`s — legal case
files — and every `Membership`. Per DESIGN.md §2a the firm is its own data controller with
its own retention obligation, and those files are exactly what GDPR Art 17(3)(b) protects.
A hard `DELETE` is not a feature; it is a way to destroy records someone is legally
required to keep.

The parallel with `User` erasure is close but not identical:

| | `User` erasure | `Organization` "deletion" |
|---|---|---|
| why the row survives | `Dossier.customer_user_id` needs an FK target | the case files themselves must survive |
| what is destroyed | the personal data on the row | **nothing** — the workspace stops being reachable |

So this is **closure, not erasure** — lifecycle, which is why it belongs in the `status`
field already deferred under YAGNI above, exactly as `closed` does for `User`. Real SaaS
does not let a tenant self-serve its own deletion either; it is an offboarding process
with export, notice and a grace period, not a button.

**Open question when closure is built:** what does a client see when their firm closes?
Under DESIGN.md §4 a customer sees an aggregate across firms. Does firm B's case vanish
from joy's portal, or persist read-only? She has a legitimate interest in her own case
history that does not end when the firm's subscription does.

## To resolve when we build

- Slug generation: `slugify(name)` + a collision suffix if taken (e.g. `-2`).
- Slug *changes* (rename) are a deliberate later feature (they break old links).
- `PATCH` and closure, per the section above — both gated on `Membership`.
