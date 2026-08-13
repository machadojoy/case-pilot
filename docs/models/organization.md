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

## To resolve when we build

- Slug generation: `slugify(name)` + a collision suffix if taken (e.g. `-2`).
- Slug *changes* (rename) are a deliberate later feature (they break old links).
