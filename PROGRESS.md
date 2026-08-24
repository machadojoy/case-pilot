# Progress

Living status + handoff notes. Update this at the end of every session.
(Stable rules live in `CLAUDE.md`; the full plan is in `PHASE1.md`.)

---

## Current status — updated 2026-08-21

**Phase:** 1 (skeleton + models + auth). **First vertical slice is closed: the API
serves real requests against Postgres.** Next model in the build order is `User`.

Current API surface:

```
GET  /health                        (unversioned — k8s probe, do not move)
POST /api/v1/organizations          201
GET  /api/v1/organizations          paginated: {items, total, offset, limit}
GET  /api/v1/organizations/{id}     200 / 404
```

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

**`User` model — build it.** Every decision it depends on is now made and written down;
this slice is pure TDD. Read `docs/models/user.md` first (nine columns, reasoning per
field), then use the `add-model` skill.

Shape, so you don't have to re-derive it:

```
id  email(unique, lowercased)  hashed_password?  full_name?
status(str + CHECK: pending|active)  email_verified_at?
sessions_valid_from?  erased_at?  created_at  updated_at
```

Three things in there are non-obvious and each has a section in the design doc:
- **`status` is a `str` + CHECK constraint, not a PG enum** — no `ALTER TYPE ... DROP
  VALUE` exists, and `unverified`/`closed` are both expected. Note `table=True` disables
  Pydantic validation, so the CHECK is the *only* enforcement. Generate it from the
  `StrEnum` so there's one source of truth. **Alembic autogenerate does not detect CHECK
  constraint changes** — write that part by hand.
- **`sessions_valid_from`** exists because DESIGN.md §5 requires invalidating sessions on
  verification and stateless JWT has nothing to invalidate.
- **`erased_at`, not soft delete** — a hidden row still holds the email (blocking
  re-registration via the unique index), the name, and a live password hash.

Then: `alembic revision --autogenerate` → hand-write the CHECK → PR.

**Scope: the table only.** No endpoints, no auth, no password hashing, no
register/login/me — those are the next slice and depend on `Membership`. The columns
that exist *for* auth (`hashed_password`, `sessions_valid_from`, `email_verified_at`)
are nullable and stay unused for now; they're here because retrofitting them later is
more expensive than carrying them. Don't build a `service.py` or `router.py` for this
slice — there's nothing for them to do yet.

**Needs the DB up:** `colima start` → `docker compose up -d` (Colima was down at the end
of this session, so pytest fails locally until you do).

Deferred, worth doing when convenient (small, independent):
- Tests build their schema with `create_all`, *not* migrations, so a broken migration
  would not fail CI. Consider switching the test schema to `alembic upgrade head`.
- `starlette.testclient` warns that `httpx` is deprecated in favour of `httpx2`.
- No auth on `POST /organizations` — anyone can create a tenant. Intentional: gating it
  needs `User` + `Membership`. Revisit when auth lands; it's an additive dependency on
  the route, not a reshape.

## Phase 1 checklist

- [x] Scaffolding: monorepo, uv, runnable API, Docker, k8s, tests, pre-commit
- [x] Local PostgreSQL via docker compose (`compose.yaml`, verified healthy)
- [x] CI (GitHub Actions: ruff lint + `ty` + pytest, with a Postgres service) + coverage
- [x] psycopg driver + `core/config.py` (pydantic-settings, reads `.env`)
- [x] `core/db.py` (engine from DATABASE_URL + session dependency)
- [x] Alembic set up + first migration (against Postgres)
- [x] Model: Organization (tenant root)
- [ ] Models: User, Membership, Jurisdiction, CaseType, Dossier
      (`User` is designed and unblocked — `docs/models/user.md`)
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
- `alembic.ini` has `post_write_hooks` running ruff over each generated revision, so
  new migrations land pre-formatted. `script.py.mako` is customized (modern typing +
  `import sqlmodel.sql.sqltypes`) — don't overwrite it by re-running `alembic init`.
- `sqlalchemy.url` in `alembic.ini` is a dummy placeholder; `env.py` overrides it from
  app settings at runtime. Editing the ini value has no effect.

## End-of-session ritual

1. Commit + push everything (WIP commits are fine — say "WIP" in the message).
2. Update **Current status**, **Next up**, and check off the checklist here.
3. Leave a breadcrumb above for anything half-done or non-obvious.
