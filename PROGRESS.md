# Progress

**The entry point.** Living status + handoff notes; update at the end of every session.

Where everything else lives: **`DESIGN.md`** = what we're building and why (domain
decisions, the source of truth); **`CLAUDE.md`** = how we work (conventions, workflow);
**`docs/schema.md`** = the ER diagram, every table and column;
**`docs/models/*.md`** + **`docs/auth.md`** = per-slice detail with reasoning;
**`PHASE1.md`** = the original brief, **historical and superseded** — background only.

## Design status (`DESIGN.md` §10)

| | Question | State |
|---|---|---|
| Q1 | Isolation: shared schema + `org_id` + **RLS** | ❓ open — not urgent until multi-tenant reads exist |
| Q2 | Customer portal: global identity + workspace switcher | 🔷 **assumed throughout** §3's union query, never formally locked |
| Q3 | Progressive identity (anonymous → lead → activated) | ✅ 2026-08-20 |
| Q4 | UUID PKs everywhere | ✅ 2026-08-13 |
| Q5 | Roles `owner/admin/lawyer/staff`; `customer` is not a role | ✅ 2026-08-20 |
| Q6 | `Jurisdiction`/`CaseType`: global vs per-firm | ❓ open — blocks reference data, not auth |

Also decided since, and easy to miss because they aren't numbered questions: **§2a** (each
firm is its own data controller; never cascade from `users` to tenant data; Art 9 data is
unavoidable here) and **§5's two mint paths** (firm staff sign up → `unverified`; clients
are captured at intake → `pending`).

---

## Current status — updated 2026-08-26

**Phase:** 1 (skeleton + models + auth). **The identity plane exists: `users` is a real
table on Postgres.** Next model in the build order is `Membership` — which, unlike
`User`, has no design doc yet, so the next step is *design*, not code.

Current API surface:

```
GET  /health                        (unversioned — k8s probe, do not move)
POST /api/v1/organizations          201
GET  /api/v1/organizations          paginated: {items, total, offset, limit}
GET  /api/v1/organizations/{id}     200 / 404
```

Done 2026-08-26 (PR #14, merged to `main`):
- **`User` model shipped** — the identity plane, nine columns, per `docs/models/user.md`.
  Table only: no router/service/schemas, because nothing can use them until `Membership`
  lands. `hashed_password` / `sessions_valid_from` / `email_verified_at` are nullable and
  unused for now; they're there because retrofitting them later costs more.
- **Two guarantees deliberately live in the database, not in application code.**
  `table=True` disables Pydantic validation in SQLModel, so a `@field_validator` on the
  model would never fire — `User(status="banana")` constructs happily. Hence:
  - `ck_users_status`, generated from the `UserStatus` StrEnum (one source of truth).
  - `uq_users_email_lower`, a **functional unique index on `lower(email)`**. Chosen over
    `unique=True` + a `.lower()` in the service: one call site forgetting to normalise
    would silently fork an identity. **Consequence for the auth slice: email lookups must
    be written `where lower(email) = :x` or they won't use the index.**
- **`TimestampMixin` was quietly broken and is now fixed.** A SQLAlchemy `Column`
  instance belongs to exactly one `Table`, and SQLModel returns an `sa_column` verbatim
  (`if isinstance(sa_column, Column): return sa_column`), so the mixin's two shared
  Column objects had bound to `organizations` and had nothing left for a second table —
  `User` failed with *"Column object 'created_at' already assigned to Table
  'organizations'"*. It was only ever correct because it had a single subclass. Now it
  passes the *recipe* (`sa_type` + `sa_column_kwargs`) so SQLModel builds a fresh column
  per subclass; `alembic check` confirms the `organizations` DDL is unchanged.
- **First two `# ty: ignore` comments in the repo**, both in `TimestampMixin`. SQLModel
  annotates `sa_type` as `type[Any]` but wants a parameterised type *instance*; the
  annotation is wrong upstream, not the call. `@declared_attr` (SQLAlchemy's canonical
  mixin answer) collides with pydantic's metaclass; a named `DateTime` subclass would
  make Alembic render `app.core.models.UTCDateTime()` into every future migration
  without an import. Both were tried and rejected — don't re-litigate.
- **`docs/models/user.md` corrected on two points the build disproved** — autogenerate
  *does* emit a CHECK on `create_table` (only *changes* go undetected), and the open
  "index on email" question is resolved.
- 28 tests, **100% coverage**. Migration round-trips; `alembic check` clean.

Done 2026-08-21 (design only — no code; all merged to `main`):
- **DESIGN.md §10 Q3 and Q5 locked.** Q3: progressive identity in *three* states —
  anonymous (no `User` row at all), lead (`pending`), activated (`active`). Email capture
  is what mints a `User`; anonymous chat is a session with `user_id NULL`. Q5: roles are
  `owner`/`admin`/`lawyer`/`staff`, and **`customer` is not a role** — that relationship is
  carried by `Dossier.customer_user_id`. Insider vs outsider are different *authorization
  shapes*, not permission levels, and a firm's own employee can be its client (which two
  `Membership` rows can't express without breaking the `(user, org)` key).
- **DESIGN.md §2a — CasePilot and each firm are separate data controllers.** Erasing a
  `User` does not erase the person; **never** `ON DELETE CASCADE` from `users` to tenant
  data; Art 9 special-category data is unavoidable in this domain, which makes the
  retention TTL on anonymous transcripts an obligation rather than housekeeping.
- **`docs/models/user.md`** — the full design. Also records why *profile* is absent:
  self-asserted (global, mutable, prefill-only) and attested (per-firm snapshot with a
  reviewer and date) are different things, and a firm's record of the facts at time of
  filing must not change when the person moves house. Build it with `Dossier`.

Done 2026-08-19 (all merged to `main`):
- **API versioning**: `app/api/v1.py` owns the `/api/v1` prefix and aggregates feature
  routers. Feature routers declare only their own prefix and stay version-agnostic, so
  a v2 is a new aggregator, not an edit to every module. `/health` stays unversioned.
- **`GET /api/v1/organizations`** — paginated via `Page[T]` + `PaginationDep` in
  `app/core/pagination.py` (`offset>=0`, `1<=limit<=100`, default 20). Ordered by
  `(created_at, id)`; the `id` tiebreaker is required because `created_at` defaults to
  `now()` = *transaction* time, so rows written together tie and pages would repeat or
  skip. `Page[T]` is a plain pydantic `BaseModel` (pure wire type; generics fight the
  SQLModel metaclass). Borrowed from the `../fastapi-tutorial` project.
- **Transaction boundary moved out of the service** — `create_organization` used to
  commit, so a signup failing after it left an orphaned tenant (no owner, slug taken).
  Services now stage only (`session.begin_nested()` + `flush()`, so a slug-collision
  retry doesn't poison the caller's transaction); the router commits. This is what makes
  the upcoming atomic signup (Organization + User + Membership) possible.
- **`POST /organizations` + `GET /organizations/{id}`** — the first real endpoint, and
  the first place the `schemas.py / service.py / router.py` module shape exists in code
  rather than only in `CLAUDE.md`. Copy this module for the next feature.
  - Slug derived server-side (`python-slugify`), never client-supplied; collisions
    suffix (`acme-legal-2`). The service **inserts and catches the unique violation**
    instead of SELECTing first — a pre-check races; the unique index is the only
    arbiter. Bounded retry, then 409.
  - Endpoints are `def`, **not `async def`** (psycopg is sync → threadpool). Keep this
    for every DB-touching path operation.
  - `name` bounded 1..200 at the API layer.
  - New `client` fixture overrides `get_session` with the test's rolled-back session so
    API tests stay isolated.
- **`ty` now runs in CI** (lint job) — was previously caught only by pre-commit.
- **`add-model` skill** (`.claude/skills/add-model/`) — the repeatable slice for adding
  a table. Use it for `User`.
- 12 tests, **100% coverage**. Verified against the running server + Postgres.

Done 2026-08-18 (branch `feat/organization-model`):
- `core/config.py` (pydantic-settings, `database_url` as `PostgresDsn` from root `.env`)
  and `core/db.py` (engine + `get_session` + `SessionDep` alias).
- `TimestampMixin` + **`Organization`** model (UUID PK, name, unique/indexed slug,
  tz-aware timestamps with `now()` server defaults).
- Test infra: dedicated `casepilot_test` DB (auto-created), per-test
  transaction-rollback `session` fixture.
- **Alembic** wired to Postgres + first migration (`6b6718274821`, creates
  `organizations`). `env.py` takes the URL from app settings; `app/models.py` is the
  model registry both autogenerate and the tests import.
- Coverage back to **100%** (4 tests) after covering `get_session` / `SessionDep`.

Done and on `main` (public: github.com/machadojoy/case-pilot):
- Monorepo (`apps/` + `packages/`), single git repo, MIT license, README.
- `apps/api`: uv + Python 3.14, minimal FastAPI app with `/health`, pytest (1 test),
  ruff + ty configured and clean; pre-commit hooks installed.
- Multi-stage non-root Dockerfile — builds & runs (verified `/health` 200).
- k8s Deployment (2 replicas) + Service — verified on the `casepilot` k3d cluster.
- **PostgreSQL 17 via docker compose** (`compose.yaml`) — up, healthy, reachable on
  localhost:5432. Decision: Postgres from day one, NOT SQLite (dev/prod parity).
- **CI green** on GitHub Actions (lint + test jobs); coverage 100% on the tiny codebase.

Known/minor (not blocking):
- CI shows a cosmetic "Node 20 deprecated" warning for `actions/checkout@v4` /
  `setup-uv@v6` — nothing fails. Bump checkout to `@v5` when convenient.
- `apps/api/README.md` is empty (0 bytes) but `pyproject` declares `readme=` — deferred.
- LICENSE is correctly detected as MIT via GitHub's REST API (the `gh repo view`
  GraphQL field just reports it lazily).

## Design pivot (2026-08-13)

We reframed the whole domain: **multi-tenant SaaS**, each law firm = an isolated
**workspace** (tenant); global `User` identity + `Membership(role)`; customers self-serve
intake; **AI agents** do triage (assess + auto-decide within firm policy, escalate edge
cases — no human intake clerk). Captured in `DESIGN.md`; per-model docs in `docs/models/`.
This **supersedes** PHASE1.md's flat data model (and its human-triage assumption).

## Next up (the very next step)

**Auth slice: `register` + `login` + `me`.** Decided 2026-08-26 — the order is *auth
first, then `Membership`*. Full build spec in **`docs/auth.md`**; read it before starting.

**`/users/me` cannot ship alone**, which is what settled the order: it needs a token →
which needs login → which needs a password → and nothing in the system can currently give
anyone one. Leads are minted `pending` with `hashed_password = None` by an intake flow
that doesn't exist. Register, login and me are one slice or they are nothing.

```
POST /api/v1/auth/register    firm-side signup -> `unverified`
POST /api/v1/auth/login       -> JWT
GET  /api/v1/users/me         the only global-plane user read
```

That forced a design decision, now recorded in DESIGN.md §5: **two populations, two mint
paths.** `register` is the *firm-side* path (a firm owner buying the SaaS); customers are
minted `pending` by intake. `pending` ≠ `unverified` — a lead's email was typed in by a
third party, so it must prove mailbox control before holding a credential; a signup-first
user already chose their own password.

Four ratified decisions, all detailed in `docs/auth.md`:

1. **Add `unverified` to `UserStatus`** — autogenerate produces an **empty migration**
   for this (it sees neither enum-value nor CHECK changes). Hand-write the
   drop/create-constraint, and prove it with `alembic upgrade head` + `\d users`;
   `create_all` in the tests will not catch a missing constraint.
2. **Login eligibility:** anyone with a password who is not erased. `pending` is refused
   structurally (no password), not by a status check.
3. **JWT** HS256, `sub`/`iat`/`exp`, secret from config — and wire the
   `iat < sessions_valid_from` rejection *now*. The column exists for it; retrofitting an
   auth check is how the pre-hijacking window gets left open.
4. **`GET /api/v1/users/me`**, not `/auth/me` (PHASE1.md is superseded).

New module `app/auth/` for credentials/tokens; `/users/me` lives in `app/users/`.

**Biggest deliberate cut:** no email sending, so no verification flow — nobody reaches
`active` yet and `unverified` is the working state. Also out: refresh tokens, password
reset, email change, rate limiting, and **authorization of any kind** (`POST
/organizations` stays open; `GET /organizations` still lists every firm to everyone —
both need `Membership`).

**Needs the DB up:** `colima start` → `docker compose up -d`.

---

**`Membership` — the slice *after* auth.** Design is **done**:
`docs/models/membership.md` (written 2026-08-26). Scope is deliberately small — rows are
created only by the org-creation flow, granting the creator `owner`; no invitations, no
member list, no removal. That still closes the live leak on `GET /organizations` and makes
`POST /organizations` authorizable. Key points:

- Shape: `(id, user_id, org_id, role)` + timestamps. **Unique on `(user_id, org_id)`.**
  Nothing else — no `invited_by`, no `status`.
- **`role` is `str` + CHECK** generated from a `StrEnum`, same as `User.status`, and the
  reasoning is stronger here because roles churn more. Autogenerate **cannot see CHECK
  changes** — hand-write it and prove it with `\d memberships`.
- **Revocation is a hard `DELETE`**, never a tombstone — a tombstone would occupy the
  `(user_id, org_id)` unique slot and block re-adding someone who left. This is the
  deliberate counter-example to `User`'s erasure.
- **Erasing a `User` deletes their memberships** — a tombstone with a live membership is a
  ghost employee with access. Not a contradiction of §2a: a membership is an *access
  grant*, a `Dossier` is a *legal record*. Grants go, records stay. The FK still must not
  be `ON DELETE CASCADE`.
- Recorded but not enforceable yet (no removal/role-change endpoints exists): **≥1 owner
  per org** (service-level — Postgres cannot express it, so don't assume it does) and
  **no self-role-change**.
- **Teams don't change this table.** DESIGN.md §3 records `Team`/`TeamMembership` as the
  decided direction, built with `Dossier` — a second axis, not a replacement. A team lead
  is `Membership(role=lawyer)` + `TeamMembership(role=lead)`. Do **not** add `lead` to
  this enum or drop the unique constraint in anticipation.

Then build it with the `add-model` skill.

**Needs the DB up:** `colima start` → `docker compose up -d`, or pytest fails locally.

Deferred, worth doing when convenient (small, independent):
- Tests build their schema with `create_all`, *not* migrations, so a broken migration
  would not fail CI. Consider switching the test schema to `alembic upgrade head`.
- `starlette.testclient` warns that `httpx` is deprecated in favour of `httpx2`.
- No auth on `POST /organizations` — anyone can create a tenant. Gating it needs only
  **authentication** (an earlier version of this note wrongly said `User` + `Membership`).
  What needs `Membership` is making creation grant its creator ownership, and scoping
  `GET /organizations` to the caller's firms — today it lists every firm to everyone.
  Both are additive to the route, not a reshape.
- **`PATCH` and `DELETE /organizations` are missing on purpose** — recorded in
  `docs/models/organization.md` so it doesn't read as an oversight. `PATCH` is a one-field
  endpoint (`name`; `slug` is the stable handle) waiting on *authorization*, so it ships
  with the `Membership` slice. `DELETE` is not a Phase 1 feature at all: deleting a tenant
  would destroy `Dossier`s the firm is legally obliged to keep (DESIGN.md §2a). The real
  operation is **closure** — lifecycle, so it belongs in `Organization.status`, like
  `closed` does for `User`.

## Phase 1 checklist

- [x] Scaffolding: monorepo, uv, runnable API, Docker, k8s, tests, pre-commit
- [x] Local PostgreSQL via docker compose (`compose.yaml`, verified healthy)
- [x] CI (GitHub Actions: ruff lint + `ty` + pytest, with a Postgres service) + coverage
- [x] psycopg driver + `core/config.py` (pydantic-settings, reads `.env`)
- [x] `core/db.py` (engine from DATABASE_URL + session dependency)
- [x] Alembic set up + first migration (against Postgres)
- [x] Model: Organization (tenant root)
- [ ] Models: ~~User~~, Membership, Jurisdiction, CaseType, Dossier
      (**`User` shipped 2026-08-26** — `docs/models/user.md`. `Membership` is next and
      still needs a design doc; build order is in DESIGN.md §Build order)
      (per DESIGN.md — supersedes PHASE1.md's flat model + the `Lawyer` M:N entity)
- [x] Endpoints: organizations (create + list + get by id), under `/api/v1`
- [ ] JWT auth: register / login / me (PyJWT + pwdlib)
- [ ] Endpoints: jurisdictions, case-types, dossiers (create/list/get mine)
- [ ] `seed.py` — jurisdictions (Work/Housing/Family), case types, lawyers
- [ ] Frontend `apps/web` (Vite + React + TS): login, submit-story form, my-dossiers list
- [ ] CORS wired for the Vite dev server

## Handoff notes / gotchas

- **Endpoint conventions** (set by `app/organizations/`, copy them):
  - Path operations are `def`, **never `async def`** — psycopg/SQLModel are sync, so
    they run in a threadpool. `async def` here blocks the event loop.
  - Use `response_model=XPublic` on the decorator with the *table* model as the return
    annotation. A bare return annotation would make `ty` reject returning the ORM object.
  - Business logic lives in `service.py`; the router only translates errors to HTTP.
  - Uniqueness: insert and catch `IntegrityError`. Never SELECT-then-INSERT — it races.
  - **Services never commit.** The router owns the transaction boundary so multi-entity
    operations stay atomic. In a service, use `session.begin_nested()` + `flush()` to
    catch an `IntegrityError` without poisoning the caller's transaction.
  - Feature routers carry only their own prefix; `app/api/v1.py` owns `/api/v1`. Add a
    new feature by adding one `include_router` line there.
  - Listing: reuse `Page[T]` / `PaginationDep` from `app/core/pagination.py`, and always
    order by a column **plus `id`** — `created_at` alone ties (`now()` is transaction
    time), which makes pages repeat or skip rows.
  - `col()` from sqlmodel when passing model attributes to `order_by` — SQLModel types
    them as their value type, so `ty` rejects them as sort keys otherwise.
  - **`User` is looked up, never enumerated.** The only global user endpoint is
    `GET /api/v1/users/me`; there is no `GET /api/v1/users`, because a global listing
    would expose every firm's client base. Anything that pages through people belongs to
    a tenant-scoped resource carrying `org_id` (staff → `Membership`, clients →
    `Dossier`). See DESIGN.md §3.
- `tests/conftest.py` imports the FastAPI app **aliased** (`app as fastapi_app`) because
  the bare name `app` is the package. Don't "simplify" that back.
- Local infra must be running for Docker/k8s work: `colima start`, then
  `k3d cluster start casepilot`. Locally-built images need
  `k3d image import <img> -c casepilot` (k3d's containerd is isolated from Colima).
- Auth libs intentionally differ from `PHASE1.md`'s suggestions: PyJWT (not python-jose),
  pwdlib (not passlib). Keep it that way.
- **DB is PostgreSQL, not SQLite** (deviation from PHASE1.md). Start it with
  `docker compose up -d` before running the app. Root `.env` (gitignored) holds creds;
  copy from `.env.example`. Creds are local-dev-only.
- **DATABASE_URL host**: `localhost:5432` works for the *host-run* dev server. When the
  app itself runs inside compose/k8s, the host becomes the Postgres *service name*
  (not localhost) — revisit when containerizing the app against Postgres.
- The `docker compose` plugin was a stale 2021 v2.2.1; symlinked brew's 5.4.0 into
  `~/.docker/cli-plugins/` (same class of fix as the docker/kubectl CLI relinks).
- **Alembic runs from `apps/api/`**: `uv run alembic revision --autogenerate -m "..."`
  then `uv run alembic upgrade head`. `alembic check` tells you if the models have
  drifted from the migrations. Requires the DB up (`docker compose up -d`).
- **New models must be imported in `app/models.py`** or autogenerate silently emits an
  empty migration. This is the single easiest way to lose an hour here.
- **Don't "simplify" `TimestampMixin` back to `sa_column=Column(...)`.** SQLModel returns
  an `sa_column` verbatim, and a Column instance belongs to exactly one Table — a shared
  one binds to whichever model inherits first and the *next* table to use the mixin dies
  with "Column object 'created_at' already assigned to Table 'organizations'". It must
  keep passing the recipe (`sa_type` + `sa_column_kwargs`). Its two `# ty: ignore`s are
  load-bearing for the same reason; `@declared_attr` and a named `DateTime` subclass were
  both tried and both cost more.
- **Alembic autogenerate emits a CHECK constraint on `create_table`, but never detects a
  *change* to one.** Adding a `UserStatus` value later produces an **empty diff** — write
  that migration by hand. Tests build their schema with `create_all`, so nothing warns.
- **Email lookups must be `where lower(email) = :x`.** Uniqueness is enforced by the
  functional index `uq_users_email_lower`, not by `unique=True` on the column, so a plain
  `where email = :x` is both case-sensitive and unable to use the index.
- `alembic.ini` has `post_write_hooks` running ruff over each generated revision, so
  new migrations land pre-formatted. `script.py.mako` is customized (modern typing +
  `import sqlmodel.sql.sqltypes`) — don't overwrite it by re-running `alembic init`.
- `sqlalchemy.url` in `alembic.ini` is a dummy placeholder; `env.py` overrides it from
  app settings at runtime. Editing the ini value has no effect.

## End-of-session ritual

1. Commit + push everything (WIP commits are fine — say "WIP" in the message).
2. Update **Current status**, **Next up**, and check off the checklist here.
3. Leave a breadcrumb above for anything half-done or non-obvious.
