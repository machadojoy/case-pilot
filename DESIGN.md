# CasePilot — Domain & System Design

Living design doc capturing the architecture we've reasoned through. Per-model detail lives
in `docs/models/`. **Supersedes the data-model sketch in `PHASE1.md`** where they differ.

Status legend: ✅ decided · 🔷 proposed (recommended, not yet locked) · ⏳ deferred seam
(later phase) · ❓ open question

## 1. Product vision

Multi-tenant SaaS for law firms. Each firm gets an isolated **workspace** (tenant); its
lawyers and staff work inside it. Prospective **customers** self-serve intake by telling
their story; **AI agents** assess and triage it into a structured dossier and — within a
firm-configured policy — auto-accept/decline or escalate edge cases to a human. ✅

## 2. Tenancy

- **Workspace = `Organization` = tenant.** The root everything scopes to. ✅
- **Isolation:** shared database, shared schema, `org_id` on every tenant-scoped row,
  reinforced with **Postgres Row-Level Security (RLS)** so the DB itself refuses
  cross-tenant reads (defense-in-depth on sensitive legal data). 🔷
- **Two planes:** *identity plane (global)* = `User`; *data plane (per-tenant)* =
  everything else, carrying `org_id`.

## 3. Identity & membership

- **`User`** — global identity/account; email **globally unique**. 🔷
- **`Membership`** — links a `User` to an `Organization` with a **`role`**. Role is
  contextual to a workspace, so it lives here, not on `User`. ✅ (structure)
- Roles (proposed): `owner`, `admin`, `lawyer`, `staff`, `customer`. ❓
- **Insider vs outsider:** staff/lawyers are insiders (see the firm's book of business);
  a `customer` is an *outsider* member who sees **only their own** case(s). ✅ (principle)

## 4. Customer experience (portal)

- **One CasePilot login, many workspaces, a switcher.** A customer with cases at two firms
  signs in once and sees both; each case's data stays isolated in its firm's workspace. 🔷
- **Privacy property (falls out for free):** the customer sees the aggregate; each firm
  sees only its own slice — a firm can't tell the customer has cases elsewhere. ✅
- Per-firm branded domains/subdomains are cosmetic and later; still one identity. ⏳

## 5. Intake funnel & case lifecycle

Entry is **per-firm** (the customer arrives via that firm's intake).

```
Discover (firm's intake) → Tell story + email (lead)
  → Agent assessment (classify, conflicts, viability, draft dossier)
  → Policy: auto-accept | auto-decline | escalate-to-human
  → Engage (agreement + conditional payment)
  → Active → Closed
```

- **Progressive identity:** capture email as a *lead* at story submission; activate the
  full account/portal at engagement. 🔷 (vs signup-first ❓)
- **Case state machine** (the `Dossier`/case backbone):
  `submitted → assessing → auto_accepted | auto_declined | needs_review → accepted |
  declined → engaged → active → closed` 🔷

## 6. Agent-driven triage

- Agents do the **assessment work** — not a human. This is the product's core value. ✅
- The firm **configures policy** (case types, jurisdictions, conflict rules, thresholds);
  the agent **applies** it per case. 🔷
- **Decide-or-escalate:** auto-decide when confident & in-policy; escalate only on
  uncertainty / conflict / high-stakes. Human = exception handler + policy author, **not**
  an intake clerk. 🔷
- **Auditability:** every agent decision is stored (recommendation, confidence, reasoning)
  — legal requires a trail. ⏳ (built Phases 2–4: classifier, then router→specialist)

## 7. Reference data (open)

`Jurisdiction` (Work/Housing/Family) and `CaseType` are likely **global** taxonomy
(shared, not org-scoped) — an intentional exception to org_id-everywhere. Or do firms
customize their own case types? ❓

## 8. Lawyer entity — superseded

PHASE1's standalone `Lawyer` reference table is replaced: **lawyers are `User`s with
`Membership(role=lawyer)`** in a firm's workspace, plus a possible `LawyerProfile`
(jurisdictions, bar #) later. ✅ (direction) / ⏳ (profile)

## 9. Deferred seams (don't build now; don't preclude)

- ⏳ Engagement + Payment/billing (Phase 5, Stripe). Conditional: retainer vs contingency.
- ⏳ Agent Assessment/Decision records + per-firm TriagePolicy (Phases 2–4).
- ⏳ Role profiles (LawyerProfile/StaffProfile), branded subdomains, chat/messages (P3).

## 10. Open questions to lock

1. ❓ Isolation: confirm shared-schema + `org_id` + **RLS**.
2. ❓ Customer portal: confirm **Option 2** (global identity + workspace switcher).
3. ❓ Identity: **progressive** (lead→activate) vs signup-first.
4. ✅ Primary keys: **UUID everywhere** (decided 2026-08-13).
5. ❓ Role set; is `customer` a `Membership` role or a distinct concept?
6. ❓ `Jurisdiction`/`CaseType`: global vs per-firm.

**Conventions (decided):** UUID PKs on all tables; `created_at` + `updated_at`
(tz-aware) on all tables.

## 11. Entity map (high level)

```
Organization (tenant) ──< Membership >── User (global identity)
Organization ──< Dossier (case) >──(customer, via Membership)
Dossier ── CaseType ── Jurisdiction            (reference data; global?)
[later] Dossier ──< Assessment/Decision >, Engagement ──< Payment >
[later] User ── LawyerProfile / StaffProfile
```

## Build order

Tenant root first: **Organization → User → Membership → (Jurisdiction/CaseType) →
Dossier**. Detailed per-model designs live in `docs/models/`.
