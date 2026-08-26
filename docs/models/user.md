# Model: User (global identity)

> Status: **core locked (2026-08-21).** Resolves DESIGN.md §10 Q3 and Q5.
> See `../../DESIGN.md` §3 (identity) and §5 (progressive identity) for the big picture.

## Purpose

The **identity plane**: one row per human, global, *never* org-scoped. One person is one
`User` no matter how many firms they touch — an employee at firm A and a client of firms
B and C is a single row with one `Membership` and two `Dossier`s.

`User` deliberately holds almost nothing. Anything on this row is visible to **every**
firm the person deals with, so it carries only what is needed to authenticate and
address an account. Personal details live per-firm (see *Profile* below).

## Fields (decided)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK. **UUID everywhere.** |
| `email` | str | **globally unique**, the identity anchor. Lowercased on write — `Joy@x.com` and `joy@x.com` are one mailbox, and without normalisation the lead flow's find-or-create silently forks the identity. **Do not** strip plus-addressing or dots: `joy+firmb@x.com` is a genuinely different mailbox, and using it to compartmentalise firms is reasonable. |
| `hashed_password` | str \| **None** | Null for leads — they have no credentials and cannot log in. pwdlib/bcrypt. |
| `full_name` | str \| None | **Display only, unverified.** One field, not first/last: name structure varies enormously across cultures (mononyms, multiple family names, varying order) and splitting buys nothing we use. Null for leads, who arrive with an email and nothing else. The *verified* legal name is per-firm. |
| `status` | str + CHECK | `pending` \| `active`. Stored as a **string with a CHECK constraint**, not a PG enum — see *Why not a native enum*. |
| `email_verified_at` | datetime \| None | Proof of **mailbox control**. Global (unlike other verification) because it anchors account ownership rather than asserting a fact about the person. |
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

`suspended` is **not** planned here: a firm never suspends a `User`, it deletes the
`Membership`. Suspension would be a platform-level action, and there is no platform-admin
concept.

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

Per DESIGN.md §4, the response must be **identical** whether the user already existed or
not. Revealing "already exists" tells firm B their prospect is shopping around.

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

### Erasing the `User` does not erase the person

Each firm is an independent controller of its own case file (DESIGN.md §2a). Firm A's
attested record still holds her legal name, address and DOB, and firm A may be legally
obliged to keep it. Her request goes to CasePilot for the account and to each firm
separately for its file. **The FK must never cascade** — `ON DELETE CASCADE` from `users`
to `dossiers` would let an identity-plane erasure destroy a firm's legal records.
Tombstoning avoids this by construction.

## Profile — deliberately not on this model

"Profile" is two different things:

| | self-asserted | attested |
|---|---|---|
| scope | global, one per person | **per-firm** |
| mutable | yes — she moves house | **no** — it is a snapshot |
| authority | none; prefill only | the firm's diligence record |

If a firm's record of an address were a pointer to a mutable global field, then the day
she moves house the firm's record of where she lived *at the time of filing* would
silently change. The snapshot is the point. Conversely, retyping an address at every firm
would hollow out §4's "one login, many workspaces" — so the self-asserted copy exists to
be **copied into** a firm's scope on submission, never read across. (Same shape as
"current shipping address" vs "the address this order shipped to".)

Per-firm attested data hangs off `Dossier` initially, graduating to a
`ClientProfile(org_id, user_id)` only if a person has several cases at one firm. Not built
now: nothing collects it yet.

"Verified" is also two mechanisms, and one boolean would conflate them:

| Kind | Proves | Lives |
|------|--------|-------|
| challenge-response (email link, SMS OTP) | control of a **channel** | `User` — global |
| document attestation (passport, utility bill) | a **fact about the person** | per-firm, with reviewer + date |

Which resolves phone: phone-as-login-channel is identity plane; phone-as-contact-detail is
the firm's record. Often the same digits, genuinely different facts.

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
  `(user, org)` unique slot forever and block re-adding someone who once left.

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
