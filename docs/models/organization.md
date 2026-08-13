# Model: Organization (the tenant / workspace)

> Discussion doc — **not final**. See `../../DESIGN.md` for the big picture.

## Purpose

The **tenant root**. One row per law-firm workspace. Every tenant-scoped table carries its
`org_id`. Created when a firm signs up; the first user becomes its `owner` (via `Membership`).

## Proposed fields (minimal core)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK (pending the UUID-vs-int lock in DESIGN.md) |
| `name` | str | display name, e.g. "XYZ Family Law" |
| `slug` | str | **unique**, URL/workspace identifier, e.g. `xyz-family-law` |
| `created_at` | datetime (tz-aware) | server default `now()` |
| `updated_at` | datetime (tz-aware) | optional; auto-updates on change |

## Deliberately NOT included yet (YAGNI)

- `status` / suspended (soft-disable) — add with an actual suspension flow.
- `plan` / billing tier — Phase 5.
- `settings` / triage policy — its own entity later.
- `owner_id` — **derive** from `Membership(role=owner)`; don't duplicate identity here.

## Open questions

1. **Slug** — include now? (Yes if we want per-workspace URLs / the switcher.)
   Auto-generate from `name`? Enforce uniqueness + immutability?
2. **`updated_at`** — adopt as a convention on all tables, or add only when needed?
3. Anything a workspace genuinely needs *at creation* beyond `name` + `slug`?
