# Auth slice — register / login / me

> Status: **designed 2026-08-26, not yet built.** Decisions ratified; this is a build spec.
> Depends on `User` (shipped, PR #14). See `models/user.md` and `../DESIGN.md` §3, §5.

## Why this slice exists at all

`GET /users/me` cannot ship alone. It needs a token → which needs login → which needs a
password → and **nothing in the system can currently give anyone one**. Leads are minted
`pending` with `hashed_password = None` by an intake flow that does not exist. So register,
login and me are one slice or they are nothing.

That forced the question DESIGN.md §5 now answers: **two populations, two mint paths.**
`POST /auth/register` is the *firm-side* path (a firm owner buying the SaaS, minted
`unverified`), not the customer path (intake email capture, minted `pending`).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/register` | firm-side signup → `unverified` |
| POST | `/api/v1/auth/login` | → JWT |
| GET | `/api/v1/users/me` | the **only** global-plane user read |

`/users/me`, **not** `/auth/me` — PHASE1.md says otherwise and is superseded. It lives in
`app/users/` so that DESIGN.md §3's rule (*`User` is looked up, never enumerated*) sits
next to the only user router there will ever be. Credentials and tokens live in a new
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

- **Login must query `lower(email) = lower(:email)`.** The unique index is functional
  (`Index("uq_users_email_lower", text("lower(email)"), unique=True)`), so a plain
  `WHERE email = :email` gets neither the index nor case-insensitivity.
- **Registering an email that already exists must not reveal that it does.** The lead flow
  has the same rule for the same reason (DESIGN.md §4) — a distinguishable response tells
  an attacker which addresses hold accounts. Same-shaped response, and mind the timing.
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
  `GET /organizations` still lists every firm to everyone. Both need `Membership`; this
  slice is authentication only.

## After this slice

`Membership` — which then makes org creation grant its creator ownership, and scopes
`GET /organizations` to firms you actually belong to.
