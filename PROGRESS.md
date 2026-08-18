# Progress

Living status + handoff notes. Update this at the end of every session.
(Stable rules live in `CLAUDE.md`; the full plan is in `PHASE1.md`.)

---

## Current status — updated 2026-08-18

**Phase:** 1 (skeleton + models + auth). **DB layer live: Organization is migrated
onto Postgres. Next model in the build order is `User`.**

Done since 2026-08-13 (branch `feat/organization-model`):
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

`Organization` is done and migrated. Build order (DESIGN.md) says **`User` is next**,
then `Membership`, then reference data, then `Dossier`.

Before writing `User`, decide the DESIGN.md §10 questions it depends on:
- Q3 progressive identity (lead→activate) vs signup-first — shapes whether `User`
  can exist without a password/verified email.
- Q5 the role set, and whether `customer` is a `Membership` role or its own concept —
  shapes `Membership` right after.
(Q1 RLS and Q6 reference-data scope can wait; Q4 UUID PKs is settled.)

Then: design doc in `docs/models/user.md` → TDD the model on a `feat/user-model`
branch → `alembic revision --autogenerate` → PR.

Deferred, worth doing when convenient (small, independent):
- **CI does not run `ty`** — the lint job runs ruff only, so type errors are caught
  solely by the local pre-commit hook. Add a `uv run ty check` step.
- Tests build their schema with `create_all`, *not* migrations, so a broken migration
  would not fail CI. Consider switching the test schema to `alembic upgrade head`.
- `starlette.testclient` warns that `httpx` is deprecated in favour of `httpx2`.

## Phase 1 checklist

- [x] Scaffolding: monorepo, uv, runnable API, Docker, k8s, tests, pre-commit
- [x] Local PostgreSQL via docker compose (`compose.yaml`, verified healthy)
- [x] CI (GitHub Actions: ruff lint + pytest, with a Postgres service) + coverage (pytest-cov)
- [x] psycopg driver + `core/config.py` (pydantic-settings, reads `.env`)
- [x] `core/db.py` (engine from DATABASE_URL + session dependency)
- [x] Alembic set up + first migration (against Postgres)
- [x] Model: Organization (tenant root)
- [ ] Models: User, Membership, Jurisdiction, CaseType, Dossier
      (per DESIGN.md — supersedes PHASE1.md's flat model + the `Lawyer` M:N entity)
- [ ] JWT auth: register / login / me (PyJWT + pwdlib)
- [ ] Endpoints: jurisdictions, case-types, dossiers (create/list/get mine)
- [ ] `seed.py` — jurisdictions (Work/Housing/Family), case types, lawyers
- [ ] Frontend `apps/web` (Vite + React + TS): login, submit-story form, my-dossiers list
- [ ] CORS wired for the Vite dev server

## Handoff notes / gotchas

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
