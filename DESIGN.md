# CasePilot — Domain & System Design

Living design doc: **what** we're building and **why**. Per-model and per-slice detail
lives in `docs/models/` (`organization.md`, `user.md`) and `docs/auth.md`.
**Supersedes `PHASE1.md`** — its data model, endpoint list and library choices — where
they differ.

**For current status and the next step, see `PROGRESS.md`** (the entry point); it also
carries an at-a-glance table of which §10 questions are still open. Conventions and
workflow live in `CLAUDE.md`.

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
- **No exceptions: `org_id` on every table, `users` included.** ✅ (Q2, 2026-08-26)
  An earlier design made `User` a *global* identity plane sitting outside tenancy; that is
  **superseded**. One uniform rule means RLS has one policy shape rather than a special
  case for the one table that broke it.

## 2a. Data protection: CasePilot holds no cross-tenant data

**Every row belongs to exactly one firm, so CasePilot is a pure processor.** ✅ (Q2,
2026-08-26) The firm is the controller of its own workspace — including its users'
accounts. There is no platform-level personal-data holding to be controller *of*.

This was not true under the superseded global-identity design, where the platform held a
cross-firm map of who was litigating where. Law firms run vendor due diligence, and "we
never hold data across our clients" is a materially easier answer than "we do, but we
don't show it to anyone."

Consequences that shape the schema:

- **An erasure or subject-access request goes to the firm**, not to CasePilot, and one
  firm's answer has no bearing on another's. Retention is that firm's obligation
  (GDPR Art 17(3)(b) commonly *requires* refusal for live legal matters).
- **Deleting a `User` still never cascades to `dossiers`.** Erasure anonymises the account
  in place; the case file survives because the firm is obliged to keep it. See
  `docs/models/user.md`.
- **Special-category data is effectively unavoidable.** Housing, family and employment
  matters routinely contain health, ethnicity or criminal-offence data — GDPR **Art 9**,
  a stricter regime than ordinary PII. The applicable condition is Art 9(2)(f), legal
  claims. This bites *before* anyone has an account: an anonymous intake transcript may
  already be Art 9 data, which turns the retention TTL on unclaimed sessions from
  housekeeping into an obligation.

## 3. Identity & membership

- **`User` is scoped to one firm.** ✅ (Q2, 2026-08-26 — **supersedes** the earlier
  global-identity model.) `users` carries `org_id`, and email is unique **per firm**, not
  globally. Someone dealing with two firms has two accounts, like every other B2B portal.
  A person's work account belongs to their employer, and ends when the job does.
- **`Membership`** — links a `User` to an `Organization` with a **`role`**. Role is
  contextual to a workspace, so it lives here, not on `User`. ✅ (structure)
- **Membership means *insider*.** Roles: `owner`, `admin`, `lawyer`, `staff`.
  ✅ (Q5, 2026-08-20)
- **`customer` is NOT a role** — the customer relationship is carried by the case:
  `Dossier(org_id, customer_user_id)`. There is no customer `Membership` row.
  ✅ (Q5, 2026-08-20)

### No cross-tenant user API ✅ (2026-08-26, restated after Q2)

There is no endpoint that pages across firms. Since Q2 this is enforced by the schema
rather than by discipline — `users.org_id` means a listing is *already* scoped — but the
rule is worth keeping explicit, because a `GET /users` that forgets its filter is the
classic tenancy bug:

| Question | Endpoint | Query over |
|---|---|---|
| who am I? | `GET /api/v1/users/me` | the caller's own row |
| who works at this firm? | `GET /api/v1/organizations/{id}/members` | `Membership` |
| who are this firm's clients? | (via cases) | `Dossier` |

**Every user query carries `org_id`.** No exceptions — that is the point of Q2.

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
  `user_id` unique key, and "what is this person's role here?" degrades from a
  value into a set that every authz check has to loop over.
- **Outsider access becomes structural.** You cannot accidentally grant org-wide scope
  to someone with no `Membership` row; the absence of the row *is* the guarantee.

The cost, accepted: authorization has two code paths. They are genuinely two
relationships — the alternative doesn't remove the second path, it hides it inside the
first.

(The cross-firm *union* query this used to need died with Q2: there is no aggregate view,
so every question is already scoped to one firm.)

### `Membership` after Q2 — deliberately kept, though it looks redundant

With `org_id` on `users`, a `Membership` collapses to `(user_id, role)` — unique on
`user_id`, one meaningful column. That is a column pretending to be a table, and it is a
fair thing to challenge. **Recommendation: keep the table anyway.** 🔷

The insider/outsider boundary is the most security-sensitive line in the system, and a
row that *exists or doesn't* cannot be forgotten the way a nullable value can. Collapsing
to `users.role IS NULL` means a client is defined by the absence of a value rather than the
absence of a grant, and it invites someone later to "tidy up" by adding `customer` as a
role value — reintroducing exactly what Q5 rejected.

The honest counter-argument: SQL NULL semantics already fail closed (`role IN (...)`
excludes NULL), the join costs a query, and one fewer table is one fewer thing. If a
reviewer prefers the collapse, the reasoning above is the thing to argue with — not
inertia from the pre-Q2 design.

### Teams — decided direction, built with `Dossier` ✅ (2026-08-26)

Firms have teams, and people hold roles *within* them. That is the target model. It does
**not** replace `Membership`; it adds a second axis on top:

| Level | Answers | Values |
|-------|---------|--------|
| `Membership(user, role)` | what you **are** at this firm | `owner` / `admin` / `lawyer` / `staff` |
| `TeamMembership(user, team, role)` | what you **do** on this team | `lead` / `member` |

A **team lead is `Membership(role=lawyer)` + `TeamMembership(role=lead)`** — still a
lawyer, which the flat model could not express. Being a lawyer is a professional fact
about the person, firm-wide; leading is a fact about one team. You do not stop being a
lawyer in another team.

**Do not fold `lead` into the role enum.** That was considered and rejected: it starts a
slide toward a job-title list (`senior_partner`, `paralegal_supervisor`…) which is not a
permission model, and it would force either a `team_lead` role that loses `lawyer`, or
set-valued roles that break the `user_id` unique key and turn every authz check
into a loop.

Three things this preserves, which is why `Membership` needs no rework:

- the flat role set of Q5 stays correct;
- the `user_id` unique constraint stays correct — no role sets;
- org-level membership survives regardless, because someone must own the firm and
  administer billing even in a two-person firm with no teams.

**Sequencing:** built alongside `Dossier`, not before. Teams organise *work*, and until
assignment exists there is nothing to check the structure against. Waiting costs nothing
— the decomposition above is additive.

Open when it is built, all better answered with a `Dossier` in front of us:

- **Are teams optional?** A two-person firm has none — so either every query carries a
  no-team path, or a default team is auto-created that serves nobody.
- **Is a case assigned to a person, a team, or both?** Probably both: owned by a team,
  worked by a person.
- **Cross-team visibility** — can a lawyer in team A see team B's cases? This is the
  expensive one: it turns scoping from `WHERE org_id = :org` into a three-level check.
- **Do teams nest?** Recommendation: no, ever.

Note also that `dossiers` currently has **no assignee column at all** — §6 escalates to a
human without saying which one. `assigned_to_user_id` (nullable FK) is the minimum, plus
an app-level check that the assignee has a `Membership` in the same org; Postgres cannot
express that as a plain FK.

## 4. Customer experience (portal)

- **One account per firm.** ✅ (Q2, 2026-08-26) A customer with matters at two firms signs
  in separately at each. This is the ordinary shape for a portal you visit occasionally —
  your bank, your utility, your doctor — and a legal matter is exactly that.
- **No workspace switcher, no aggregate view.** Explicitly rejected; see §10 Q2 for the
  option that was considered and why it lost.
- **Privacy is now structural, not a property to maintain.** A firm cannot tell whether
  its client has matters elsewhere because *no link exists* — not because we are careful
  not to expose it. Nor can the platform.
- **The reverse is available later and is additive:** an optional `person_id` linking rows
  a customer chooses to connect would make a switcher an opt-in feature. Going the other
  way — global identity split back into per-firm rows — is a teardown. This is why Q2 went
  the reversible direction. ⏳
- Per-firm branded domains/subdomains are cosmetic and later. ⏳

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

  Since Q2, both paths mint a `User` **inside one firm**. The same email at two firms is
  two unrelated rows, so there is no cross-firm find-or-create and no way to probe whether
  someone holds an account elsewhere. Within a single firm the non-revealing response rule
  still applies: firm A's intake must not disclose that firm A already knows this email.

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
2. ✅ Identity scope: **per-firm accounts** (2026-08-26). `users` carries `org_id`;
   email is unique per firm; no workspace switcher.
   **Rejected: global identity + switcher.** It was the elegant model — a person is a
   person — but it made the platform a controller of a cross-firm map of who is litigating
   where, forced `users` to be the one table without `org_id` (the exception that
   complicates every RLS policy), and required the identity/data plane split, an erasure
   fan-out across controllers, a union query for the switcher, and a cross-firm
   find-or-create with its account-enumeration surface. It bought an aggregate view for
   the minority of people with matters at two firms at once. Per-firm is also the
   **reversible** direction (see §4).
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
Organization (tenant) ──< User (org-scoped account; email unique per firm)
                              │
                              ├──< Membership (role)  insiders only — absence = outsider
                              └──< Dossier.customer_user_id   the client link

Organization ──< Dossier (case)                (full ER diagram: docs/schema.md)
Dossier ── CaseType ── Jurisdiction            (reference data; global?)
[later] Dossier ──< Assessment/Decision >, Engagement ──< Payment >
[later] User ── LawyerProfile / StaffProfile
```

## Build order

Tenant root first: **Organization → User → Membership → (Jurisdiction/CaseType) →
Dossier**. Detailed per-model designs live in `docs/models/`.
