# Model: User (an account at one firm)

> Status: **core locked (2026-08-21); rescoped by Q2 (2026-08-26).**
> Q2 made accounts **per-firm** — this doc previously described a global identity plane.
> Resolves DESIGN.md §10 Q2, Q3 and Q5.
> See `../../DESIGN.md` §3 (identity) and §5 (progressive identity) for the big picture.

## Purpose

An account **at one firm**. `users` carries `org_id` like every other table (DESIGN.md
§2); someone dealing with two firms has two unrelated rows, and nothing links them. That
is what makes CasePilot a pure processor rather than the holder of a cross-firm map of who
is litigating where (§2a).

**Superseded:** an earlier design made `User` a global identity plane outside tenancy,
with a workspace switcher. See §10 Q2 for what that cost and why it lost.

`User` still deliberately holds almost nothing — only what is needed to authenticate and
address an account. Verified personal details are *attested* data belonging to the case,
not the account (see *Profile* below).

## Fields (decided)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK. **UUID everywhere.** |
| `org_id` | UUID | FK → `organizations.id`. The firm this account belongs to. Added by Q2. |
| `email` | str | Unique **per firm** — `(org_id, lower(email))`, not globally. The same address at two firms is two unrelated accounts. The identity anchor within a workspace. Lowercased on write — `Joy@x.com` and `joy@x.com` are one mailbox, and without normalisation the lead flow's find-or-create silently forks the account. **Do not** strip plus-addressing or dots: `joy+firmb@x.com` is a genuinely different mailbox. |
| `hashed_password` | str \| **None** | Null for leads — they have no credentials and cannot log in. pwdlib/bcrypt. |
| `role` | str \| None + CHECK | `owner` \| `admin` \| `lawyer` \| `staff`, or **`NULL` = not staff** (a client). See *Roles* below. Was a separate `Membership` table until 2026-08-26. |
| `full_name` | str \| None | **Display only, unverified.** One field, not first/last: name structure varies enormously across cultures (mononyms, multiple family names, varying order) and splitting buys nothing we use. Null for leads, who arrive with an email and nothing else. The *verified* legal name is per-firm. |
| `status` | str + CHECK | `pending` \| `unverified` \| `active`. Stored as a **string with a CHECK constraint**, not a PG enum — see *Why not a native enum*. |
| `email_verified_at` | datetime \| None | Proof of **mailbox control** — what makes the account usable, as opposed to attested facts *about* the person, which belong to the case. |
| `sessions_valid_from` | datetime \| None | Reject any JWT whose `iat` is older than this. **Required by DESIGN.md §5** — see *Session invalidation*. |
| `erased_at` | datetime \| None | Set when the identity is destroyed in place. See *Erasure*. |
| `created_at` / `updated_at` | datetime (tz-aware) | Convention: both on every table. |

### Status values

| Value | Means |
|-------|-------|
| `pending` | A **lead** — email captured at a firm's intake, no credentials, cannot authenticate. |
| `unverified` | **Signup-first** (firm staff): chose their own password, mailbox not yet proven. Decided 2026-08-26; ships with the auth slice — see `../auth.md`. |
| `active` | Verified email + password. Full portal access. |

`pending` and `unverified` look similar and are not: a lead's email was typed in by a
*third party* at some firm's intake, so it must prove mailbox control **before** it may
hold a credential. A signup-first user already chose their own password. Two populations,
two mint paths — DESIGN.md §5.

**Login eligibility** (decided 2026-08-26): anyone holding a password who is not erased —
so `unverified` and `active` may log in. `pending` is refused *structurally* rather than
by a status check, since it has no password to verify against.

One value named but **deliberately not built**:

- `closed` — voluntary account closure. Closure *is* lifecycle (a dormant account whose
  data is intact), which is why it belongs here and erasure does not. Add with the flow.

`suspended` is **not** planned: a firm revoking someone sets `closed` (see *Revocation*
below). A platform-level suspension would be a different thing, and there is no
platform-admin concept.

### Roles

| Value | Means |
|-------|-------|
| `owner` | Owns the firm. **At least one per organization**, always. |
| `admin` | Administers the workspace. |
| `lawyer` | Does legal work; can be assigned cases. |
| `staff` | Works at the firm, not a lawyer. |
| **`NULL`** | **Not staff** — a client. Not a grant, just the absence of one. |

**`customer` is not a value and must never become one** (DESIGN.md §10 Q5). Insider and
outsider are different *authorization shapes*: an insider is scoped
`WHERE org_id = :org`, an outsider `WHERE org_id = :org AND customer_user_id = :me`. No
role check can express the second, so a `customer` value would leave the row-level
constraint living wherever someone remembered to write it. `NULL` fails closed —
`role IN ('lawyer', 'staff')` excludes it automatically.

It also keeps the firm's-own-employee-is-a-client case representable: `role = 'lawyer'`
plus a `Dossier` where she is the customer. As a role *value* she could not be both.

`role` gets the same `str` + CHECK treatment as `status`, and the reasoning is stronger —
roles churn more than statuses. Generate the constraint from the `StrEnum`.

### Rules to enforce when the endpoints exist

None of these can be violated yet — there is no role-change or revocation endpoint — so
they are recorded now and enforced when each lands.

- **At least one `owner` per organization.** An org with zero owners is orphaned and
  unadministrable. This is a cross-row constraint: **Postgres does not guarantee it**, and
  a simple `CHECK` cannot express it. Enforce in the service, and do not let a future
  reader assume the database has it covered. A firm may have several owners
  (co-founders), which is why the invariant is *at least* one.
- **No self-role-change.** An `admin` promoting themselves to `owner` is privilege
  escalation.
- **Revocation closes the account.** When someone leaves, `role = NULL` is *not enough* —
  it leaves an account indistinguishable from a client's, so a former employee keeps a
  live login as an outsider. Set `status = 'closed'`. **Exception:** if they are also a
  client of the firm (they appear as `customer_user_id` on a `Dossier`), null the role and
  keep the account — they stop being staff and remain a client.

### Why not a native enum

Postgres has no `ALTER TYPE ... DROP VALUE` — removing a value means renaming the type,
recreating it, casting the column, dropping the old one. We are still in design churn and
already expect `unverified` and `closed`, so some guesses will be wrong. With a CHECK
constraint, both adding and removing are symmetric one-line DDL.

Generate the constraint from the `StrEnum` so there is one source of truth:

```python
CheckConstraint(
    "status IN ({})".format(", ".join(f"'{s}'" for s in UserStatus)),
    name="ck_users_status",
)
```

**Autogenerate emits a CHECK on `create_table` but never detects a *change* to one.**
Verified when building this (2026-08-26): the initial migration rendered
`sa.CheckConstraint("status IN ('pending', 'active')", ...)` on its own. Adding
`unverified` later will produce an empty diff, so that one is hand-written — and since
tests build their schema with `create_all` rather than migrations, nothing warns you.

Note also that `table=True` **disables Pydantic validation** in SQLModel, so annotating
the attribute as `UserStatus` gives no runtime guarantee — `User(status="banana")`
constructs happily. The CHECK constraint is not belt-and-braces here; it is the only
actual enforcement. Hence `status: str` in the model, with `UserStatus` used at call
sites for ergonomics.

## Progressive identity (three states)

Signup is not a gate — you can arrive, chat and leave without an account.

| State | `User` row? | Credentials | Born when |
|-------|-------------|-------------|-----------|
| anonymous | **none** | — | lands on a firm's intake, chats, leaves |
| lead | `pending` | none | gives an email to get an answer back |
| activated | `active` | password + verified email | engagement (portal access) |

**Email capture is what mints a `User`.** Anonymous chat is a server-side session with
`user_id NULL`; with no email there is nothing to identify, and a "ghost user" would have
no value for the unique email column.

### Find-or-create is a race

Two intake submissions with the same email can land concurrently: both find nothing, both
insert, one gets an `IntegrityError`. Same insert-and-catch discipline as
`create_organization`, but with a twist — on the violation, **re-select and use the
existing row** rather than retrying with a new value. Inside `session.begin_nested()`, and
the service still must not commit.

The response must be **identical** whether the account already existed or not. Since Q2
this is no longer about hiding that someone deals with *other* firms — there is no
cross-firm link to leak — but a distinguishable response still lets anyone probe which
addresses this firm holds, which for a law firm is a client list.

### A `pending` user must be unusable

It cannot authenticate, cannot be granted anything, and receives only verification links —
**never case content**. Anyone can submit *your* email at any firm's intake, so activation
is "prove you control the mailbox, *then* set a password", never "set a password on the
existing row". On verification, bump `sessions_valid_from` to invalidate everything
predating the claim (pre-hijacking mitigation, Sudhodanan & Paverd, USENIX Sec '22).

## Session invalidation

DESIGN.md §5 requires invalidating all sessions on verification — but PHASE1 plans
**stateless JWT**, where there is nothing to invalidate and a token issued before the
claim stays valid until it expires. That is precisely the pre-hijacking window.

`sessions_valid_from` closes it: the auth dependency rejects any token with
`iat < sessions_valid_from`, and invalidating everything is one `UPDATE`. The cost is that
JWT becomes stateless-*ish* — the user row is needed on every authenticated request.

The production alternative is short-lived access tokens (~15 min) plus DB-stored refresh
tokens, so only the refresh path touches the database. Deferred: the column is needed
under either design, and it is far cheaper now than retrofitting a token store.

## Erasure (not soft delete)

Two different endings, and they are **not** alternatives:

| | What it is | How |
|---|---|---|
| account closure | lifecycle — dormant, data intact, reversible | a `status` value (`closed`), when the flow exists |
| erasure (GDPR Art 17) | the identity is destroyed, irreversible | `erased_at` + overwrite the fields |

Soft delete cannot serve as erasure. A hidden row still holds the email (still occupying
the unique index, so the person can never re-register), the name, and a live password
hash. Regulators do not accept a flag: the accepted route is **anonymisation**, after
which the data is out of scope entirely (Recital 26). Pseudonymisation — hiding,
tokenising, flagging — explicitly does not count.

On an erasure request:

```
email               → 'erased-{id}@invalid'   -- RFC 2606 reserved; can never route
hashed_password     → NULL
full_name           → NULL
sessions_valid_from → now()                   -- kills any live JWT
erased_at           → now()
```

`id` and `created_at` survive because `Dossier.customer_user_id` points here and the case
is a legal record. `status` is **left alone** — it costs nothing and records what the
person was.

Deriving the tombstone email from the row's own `id` makes it deterministic and
collision-free. Overwriting rather than nulling is deliberate twice over: `NULL` would
collide under the unique index on the second erasure, and the real address must be
**freed** so the person can register again later — they would get a fresh `User` with no
link to the old cases, which is what erasure means.

**Always tombstone, never hard-delete**, even for a user with no cases: a "do they have
cases?" check races against a case being created, and one code path beats two.

### Erasing the account does not erase the case file

The firm is the controller of both (DESIGN.md §2a), and the two have different answers.
The account can be anonymised on request; the `Dossier` often **must not** be — Art
17(3)(b) protects retention for live legal claims, and the case file still holds her
attested legal name, address and DOB.

**The FK must never cascade.** `ON DELETE CASCADE` from `users` to `dossiers` would let an
account erasure destroy records the firm is obliged to keep. Tombstoning avoids this by
construction.

Since Q2 the request no longer fans out across controllers — it goes to *that firm*, and
another firm's copy of the same person is a separate matter that firm decides separately.

## Profile — deliberately not on this model

Q2 simplified this. The old design had *two* profiles — a global self-asserted copy for
prefill, and a per-firm attested snapshot — because one person spanned many firms. With
per-firm accounts there is only one kind left:

**Attested data belongs to the case, not the account.** Legal name, address, DOB and
phone-as-contact-detail are facts a firm *verified*, with a reviewer and a date. They hang
off `Dossier` initially, graduating to a `ClientProfile(org_id, user_id)` only if a person
has several cases at one firm.

The reason it is not on `users` even now that both are org-scoped: **the firm's record must
be a snapshot.** If it pointed at a mutable account field, then the day she moves house the
firm's record of where she lived *at the time of filing* would silently change. That is
the whole point of holding it. (Same shape as "current shipping address" vs "the address
this order shipped to" — the order does not join to the profile.)

Not built now: nothing collects it yet.

"Verified" is also two mechanisms, and one boolean would conflate them:

| Kind | Proves | Where |
|------|--------|-------|
| challenge-response (email link, SMS OTP) | control of a **channel** | `users` — it is what makes the account usable |
| document attestation (passport, utility bill) | a **fact about the person** | the case record, with reviewer + date |

Which resolves phone: phone-as-login-channel is an account credential;
phone-as-contact-detail is attested case data. Often the same digits, genuinely different
facts — and note the second does *not* transfer between firms even now that accounts are
separate, because each firm did its own diligence.

## Deliberately NOT included yet (YAGNI)

- **Address / phone / DOB / legal name** — per-firm attested data, above. Note when built:
  one E.164 string for phone (never a separate country-code column); **do not** model
  addresses as street/city/state/zip (a Western assumption that breaks
  internationally) — freeform lines plus ISO 3166-1 alpha-2, structuring only country and
  region because `Jurisdiction` routing queries them.
- **National ID / SSN** — not until something concretely requires it. Encryption at rest,
  an Art 34 breach-notification trigger, and pure liability otherwise.
- **Multiple phones/addresses** — one of each until someone asks for a second.
- `pending_email` — needed for **email change**, which must verify the new address
  *before* switching or a typo is permanent lockout. With auth.
- Password reset — note the sharp interaction: reset on a `pending` user **is** the
  activation path, so they must not be two flows that disagree.
- `failed_login_attempts` / `locked_until` — with a real brute-force concern.
- `locale` / `timezone` — with notifications.
- Anonymous-session/transcript model — with chat. See DESIGN.md §9.
- `deleted_at`/soft-delete **mixin** — one table needs erasure today. Extract on the
  second use, and name it for the operation (`ErasureMixin` for destroy-in-place vs
  `ArchiveMixin` for hide-but-keep); one mixin doing both invites an "undelete" endpoint
  against rows whose contents no longer exist. Note `Membership` is the likely *counter*
  example: revocation should be a real `DELETE`, since a tombstone would occupy the
  `user_id` unique slot forever and block re-adding someone who once left.

## To resolve when we build

- ~~Index: unique on `email` (the lowercased value).~~ **Resolved (2026-08-26):** a
  functional unique index, `Index("uq_users_email_lower", text("lower(email)"),
  unique=True)`, rather than `unique=True` on the column plus a `.lower()` in the
  service. Same reasoning as the CHECK above — `table=True` disables Pydantic
  validation, so a `@field_validator` on the model would never fire and normalisation
  would rest entirely on every call site remembering. The database is the only arbiter.
  Consequence for the service slice: lookups must be written `where lower(email) = :x`
  to use the index. No index on `status` — low cardinality.
- Whether `full_name` is captured from the intake chat or asked for explicitly.
