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

## 2a. Data protection: who controls what

CasePilot and its firms are **different data controllers**, and this is structural, not
paperwork. ✅ (2026-08-21)

| Plane | Controller | Erasure on request? |
|-------|-----------|---------------------|
| identity (`User`) | **CasePilot** | yes — anonymise in place, see `docs/models/user.md` |
| data (`Dossier`, attested profile) | **each firm, independently** | often **must be refused** — GDPR Art 17(3)(b), retention for legal claims |

Consequences that shape the schema:

- **Erasing a `User` does not erase the person.** The account is anonymised; each firm's
  case file is governed by that firm's own retention obligation. A subject access or
  erasure request fans out to CasePilot *and* to every firm separately.
- **No `ON DELETE CASCADE` from `users` to tenant data** — ever. An identity-plane
  erasure must not be able to destroy a firm's legal records.
- **Attested personal details are per-firm** — for privacy (§4) *and* because retention
  periods differ per firm, so a global profile row would have no single lawful lifetime.
- **Special-category data is effectively unavoidable.** Housing, family and employment
  matters routinely contain health, ethnicity or criminal-offence data — GDPR **Art 9**,
  a stricter regime than ordinary PII. The applicable condition is Art 9(2)(f), legal
  claims. Note this bites *before* anyone has an account: an anonymous intake transcript
  may already be Art 9 data, which turns the retention TTL on unclaimed sessions from
  housekeeping into an obligation.

## 3. Identity & membership

- **`User`** — global identity/account; email **globally unique**. Never org-scoped:
  one human is one `User` no matter how many firms they touch. ✅ (Q3, 2026-08-20)
- **`Membership`** — links a `User` to an `Organization` with a **`role`**. Role is
  contextual to a workspace, so it lives here, not on `User`. ✅ (structure)
- **Membership means *insider*.** Roles: `owner`, `admin`, `lawyer`, `staff`.
  ✅ (Q5, 2026-08-20)
- **`customer` is NOT a role** — the customer relationship is carried by the case:
  `Dossier(org_id, customer_user_id)`. There is no customer `Membership` row.
  ✅ (Q5, 2026-08-20)

### No tenant-agnostic user API ✅ (2026-08-26)

The **only** global-plane user endpoint is `GET /api/v1/users/me`.

There is no `GET /api/v1/users`. A global listing would expose every firm's client base
to anyone authenticated — the exact inverse of §4's privacy property. Everything about
*other* people is reached through org scope, never through `User`:

| Question | Endpoint | Really a query over |
|---|---|---|
| who am I? | `GET /api/v1/users/me` | `User` (the one global read) |
| who works at this firm? | `GET /api/v1/organizations/{id}/members` | `Membership` |
| who are this firm's clients? | (via cases) | `Dossier` |

The rule to hold onto: **`User` is looked up by identity, never enumerated.** If an
endpoint would let you page through people, it belongs to a tenant-scoped resource and
must carry `org_id`.

### Why `customer` is a distinct concept, not a role

Insider and outsider are not two permission levels, they are two **authorization
shapes**:

| | scope predicate |
|---|---|
| insider (has a `Membership`) | `WHERE org_id = :org` — the firm's book of business |
| outsider (has a `Dossier`) | `WHERE org_id = :org AND customer_user_id = :me` |

No role check can express that second predicate, so folding `customer` into the role
enum would leave the row-level constraint living wherever someone remembered to write
it — a client-list leak waiting to happen. Three further reasons:

- **It can't drift.** "joy is a client of firm B" *means* "joy has a case at firm B".
  A `Membership(customer)` row stores that fact a second time, so it can disagree.
- **A firm's own employee can be its client.** joy as `lawyer` *and* client at firm A
  is one `Membership` + one `Dossier`. As two membership rows it breaks the natural
  `(user, org)` unique key, and "what is this person's role here?" degrades from a
  value into a set that every authz check has to loop over.
- **Outsider access becomes structural.** You cannot accidentally grant org-wide scope
  to someone with no `Membership` row; the absence of the row *is* the guarantee.

The cost, accepted: the workspace switcher is a union rather than one query, and
authorization has two code paths. They are genuinely two relationships — the
alternative doesn't remove the second path, it hides it inside the first.

```sql
SELECT org_id FROM memberships WHERE user_id = :me          -- firms I work at
UNION
SELECT DISTINCT org_id FROM dossiers WHERE customer_user_id = :me  -- firms I'm a client of
```

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

- **Progressive identity — decided.** ✅ (Q3, 2026-08-20). Signup is not a gate: you can
  arrive, chat, and leave without an account. Three states, not two:

  | state | `User` row? | credentials | born when |
  |---|---|---|---|
  | **anonymous** | ❌ none | — | lands on a firm's intake, chats, leaves |
  | **lead** | ✅ `pending` | none | gives an email to get an answer back |
  | **activated** | ✅ `active` | password + verified email | engagement (portal access) |

  **Email capture is what mints a `User`.** Anonymous chat is a server-side session with
  `user_id NULL` — no email means nothing to identify, and a "ghost `User`" would have
  no value for the globally-unique email column. `User` therefore needs a nullable
  `hashed_password`, an explicit `status`, and `email_verified_at`.

  **Two mint paths, for two populations.** ✅ (2026-08-26) A `User` row is created either
  by signup or by intake, and conflating them is what `PHASE1.md` got wrong:

  | Population | How they arrive | Minted as | Threat model |
  |---|---|---|---|
  | **firm staff** — a firm buying the SaaS | marketing site, **signs up** | `unverified` | they chose their own password; they merely haven't proven the mailbox |
  | **clients** — that firm's prospects | **intake** email capture | `pending` | *anyone* can type your email into a firm's intake form |

  A firm owner never comes through intake — intake is for *their* clients. So
  `POST /auth/register` does exist, but only as the **firm-side** path; it is emphatically
  not how a customer becomes a user.

  **`pending` ≠ `unverified`, and the difference is the whole point.** A lead is
  powerless because its email was supplied by a third party, so activation must be "prove
  mailbox control, **then** set a password" — never "set a password on the existing row".
  A signup-first user already holds a credential nobody else chose.

  `PHASE1.md`'s single `POST /auth/register` is still superseded: it assumed one flat path
  for everyone, which would let a customer be minted with a self-chosen password and skip
  the proof-of-control rule entirely.

  Protocol at each transition (all three are standard practice, not invention):

  1. **Anonymous → lead:** find-or-create `User` by email, re-parent the transcript, and
     **rotate the session token** — OWASP requires regenerating the session id on any
     privilege change; skipping it is session fixation. Return the *same* response
     whether the user already existed or not (see §4's privacy property: revealing
     "already exists" tells firm B their prospect is shopping around).
  2. **A `pending` user is unusable.** It cannot authenticate, cannot be granted
     anything, and receives only verification links — never case content. This is what
     makes lead rows safe: anyone can submit *your* email at any firm's intake, so
     activation must be "prove you control the mailbox, *then* set a password", never
     "set a password on the existing row".
  3. **On verification, invalidate everything predating the claim** (sessions, tokens).
     Stateless JWT has nothing to invalidate, so this needs a mechanism:
     `User.sessions_valid_from`, rejecting any token whose `iat` is older.
     This is the pre-hijacking mitigation (Sudhodanan & Paverd, USENIX Sec '22): the
     nasty variant is a squatter's session surviving the victim's later signup.
  4. Unclaimed anonymous sessions get a **retention TTL** — a transcript is personal
     data even without a name.

  Consequence accepted: the anonymous transcript *is* back-filled onto the lead, so the
  session cookie is effectively a bearer credential for it. The never-email-content rule
  is what bounds the blast radius.
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
- ⏳ **Profile is two things**, and collapsing them is expensive to undo: a *self-asserted*
  global copy the person maintains (prefill only, never authoritative) and a *per-firm
  attested* snapshot with a reviewer and a date. The firm's record must not be a pointer
  to a mutable global field, or its record of the facts *at time of filing* changes when
  she moves house. Detail in `docs/models/user.md`; build with `Dossier`.
- ⏳ Anonymous chat sessions (`user_id NULL`) + transcript back-fill on identify, with a
  retention TTL. Constrained by Art 9 (§2a) before it is built.

## 10. Open questions to lock

1. ❓ Isolation: confirm shared-schema + `org_id` + **RLS**.
2. ❓ Customer portal: confirm **Option 2** (global identity + workspace switcher).
3. ✅ Identity: **progressive**, in three states — anonymous (no `User`) → lead
   (`pending`) → activated (`active`). Decided 2026-08-20; see §5.
4. ✅ Primary keys: **UUID everywhere** (decided 2026-08-13).
5. ✅ Roles are `owner` / `admin` / `lawyer` / `staff`; **`customer` is a distinct
   concept**, carried by `Dossier.customer_user_id`, not a `Membership` row.
   Decided 2026-08-20; see §3.
6. ❓ `Jurisdiction`/`CaseType`: global vs per-firm.

**Conventions (decided):** UUID PKs on all tables; `created_at` + `updated_at`
(tz-aware) on all tables.

## 11. Entity map (high level)

```
Organization (tenant) ──< Membership >── User (global identity)   insiders only
Organization ──< Dossier (case) ── customer_user_id ──> User      the customer link
Dossier ── CaseType ── Jurisdiction            (reference data; global?)
[later] Dossier ──< Assessment/Decision >, Engagement ──< Payment >
[later] User ── LawyerProfile / StaffProfile
```

## Build order

Tenant root first: **Organization → User → Membership → (Jurisdiction/CaseType) →
Dossier**. Detailed per-model designs live in `docs/models/`.
