# Auth slice — register / login / me

> Status: **designed 2026-08-26; reshaped the same day by Q2** (per-firm accounts).
> The slice is now bigger than "register/login/me" — see *What Q2 changed*. Build spec,
> but the scope change wants your sign-off first. 🔷
> Depends on `User` (shipped, PR #14). See `models/user.md` and `../DESIGN.md` §3, §5.

## Why this slice exists at all

`GET /users/me` cannot ship alone. It needs a token → which needs login → which needs a
password → and **nothing in the system can currently give anyone one**. Leads are minted
`pending` with `hashed_password = None` by an intake flow that does not exist. So register,
login and me are one slice or they are nothing.

That forced the question DESIGN.md §5 now answers: **two populations, two mint paths.**
`POST /auth/register` is the *firm-side* path (a firm owner buying the SaaS, minted
`unverified`), not the customer path (intake email capture, minted `pending`).

## What Q2 changed 🔷

Accounts are now scoped to a firm (`users.org_id`), which has two consequences the
original spec did not account for.

### 1. A `User` cannot exist before its firm does

Pre-Q2, `register` minted a global identity and creating a firm came later. Now every
account needs an `org_id`, so **the first user of a new firm must be created together with
the firm** — there is nothing to scope them to otherwise.

So firm-side registration *is* firm creation: `Organization` + `User(role='owner')` in one
transaction, all-or-nothing, the router owning the boundary. That is exactly what
DESIGN.md calls *creation is transactional*.

**This no longer drags `Membership` into the slice.** An earlier version of this spec said
it did, and proposed merging the auth and `Membership` slices to cope. That went away when the
`Membership` table was collapsed into `users.role` (DESIGN.md §3, 2026-08-26) — the owner grant
is now a column value set during the same `INSERT`, not a second table to populate. The
slice is back to three endpoints.

### 2. Login needs to know which firm

`joy@x.com` may exist at several firms as unrelated accounts, so email alone no longer
identifies anyone. Options considered: subdomain (`acme.casepilot.com` — DESIGN.md §4 calls
branded domains cosmetic and later), path-scoping every route under
`/api/v1/orgs/{slug}/…` (a bigger reshape of endpoints that already exist), or an
`org_slug` field in the request body.

**Recommendation: `org_slug` in the body** for `register` and `login` only. Cheapest, no
reshape, and it moves to subdomain routing later without changing the token design.

**The JWT then carries `org_id`**, so every subsequent request knows its tenant without
repeating it — and the auth dependency can reject a token whose `org_id` does not match the
resource being touched. Add `org_id` to the claims alongside `sub`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/register` | **firm signup**: Organization + User(`role='owner'`, `status='unverified'`), one transaction |
| POST | `/api/v1/auth/login` | `org_slug` + email + password → JWT carrying `sub` and `org_id` |
| GET | `/api/v1/users/me` | the caller's own row |

Registering an *additional* user into an existing firm is **not** in this slice — that is
the invitation flow, which needs an `Invitation` entity and a mailer.

`/users/me`, **not** `/auth/me` — PHASE1.md says otherwise and is superseded. It lives in
`app/users/`, next to the rule that every user query carries `org_id` (DESIGN.md §3). Credentials and tokens live in a new
`app/auth/` module.

Both feature routers carry only their own prefix; `app/api/v1.py` owns `/api/v1`.

## Decisions (ratified 2026-08-26)

1. **Add `unverified` to `UserStatus`.** Autogenerate detects neither enum-value nor
   CHECK-constraint changes, so `alembic revision --autogenerate` will produce an **empty
   migration**. Hand-write it:

   ```python
   def upgrade() -> None:
       op.drop_constraint("ck_users_status", "users", type_="check")
       op.create_check_constraint(
           "ck_users_status", "users",
           "status IN ('pending', 'unverified', 'active')",
       )
   ```

   `downgrade()` is the mirror. Tests build their schema with `create_all`, so a missing
   constraint fails nothing — `alembic upgrade head` then `\d users` is the only proof.

2. **Who may log in:** anyone holding a password who is not erased. `unverified` and
   `active` yes; `pending` is refused *structurally* — there is no password to verify, so
   no status check is needed for it. Erased rows must be refused explicitly
   (`erased_at IS NOT NULL`), since erasure nulls the password anyway but the check
   should not depend on that ordering.

3. **Token:** HS256, `sub` = user id, `iat`, short `exp`. Secret from `core/config.py`,
   never a literal. **Wire the `iat < sessions_valid_from` rejection now**, not later —
   the column exists precisely for it (DESIGN.md §5), and retrofitting an auth check is
   how the pre-hijacking window gets left open.

4. **`GET /api/v1/users/me`**, per DESIGN.md §3.

## Gotchas specific to this slice

- **Login must query `org_id = :org AND lower(email) = lower(:email)`.** The index is
  functional *and* now composite — `(org_id, lower(email))` — so a plain
  `WHERE email = :email` gets neither the index, nor case-insensitivity, nor tenant
  isolation. Missing the `org_id` term would let a password from firm A authenticate
  against firm B's account with the same address. **This is the sharpest bug in the slice.**
- **Registering an email that already exists must not reveal that it does.** Since Q2 this
  is no longer about hiding cross-firm relationships — there are none — but a
  distinguishable response still lets anyone enumerate which addresses a given firm holds,
  which for a law firm is a client list. Same-shaped response, and mind the timing.
- **Never say *which* credential was wrong** on login. One error for both.
- **`table=True` disables Pydantic validation**, so the `UserCreate` *schema* (not the
  table model) is what enforces password length and email format.
- Password hashing is **pwdlib[bcrypt]** — not passlib (unmaintained). PyJWT, not
  python-jose. CLAUDE.md is explicit and PHASE1.md's suggestion is stale.
- Path operations are `def`, never `async def`. Services never commit; the router owns
  the transaction boundary.

## Deliberately NOT in this slice

Each of these is named so it is a deferral, not an oversight:

- **Email sending and the verification flow.** No mailer exists, so nobody reaches
  `active` yet — `unverified` is the working state for now. This is the largest and most
  deliberate cut.
- **Refresh tokens.** `sessions_valid_from` covers invalidation; the short-lived
  access + DB-stored refresh design is the production shape and can come later
  (`models/user.md`).
- **Password reset.** Note the trap when it lands: reset on a `pending` user *is* the
  activation path, so the two must not be separate flows that disagree.
- **Email change** (`pending_email`), **login rate limiting / lockout**, **`closed`
  status**.
- **Authorization of any kind.** `POST /organizations` stays open, and
  `GET /organizations` still lists every firm to everyone. Scoping them is authorization,
  which this slice deliberately does not do — but note `register` does now make
  `POST /organizations` redundant for firm signup.

## After this slice

**Authorization.** `register` grants ownership, but nothing yet *checks* a role. Next is
the dependency that reads `role` off the token's user and gates the org endpoints —
scoping `GET /organizations` and closing the anonymous `POST`.

Then invitations (a second person joining a firm), which needs an `Invitation` entity and
a mailer.
