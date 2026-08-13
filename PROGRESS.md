# Progress

Living status + handoff notes. Update this at the end of every session.
(Stable rules live in `CLAUDE.md`; the full plan is in `PHASE1.md`.)

---

## Current status — updated 2026-08-13

**Phase:** 1 (skeleton + models + auth). **Scaffolding + DB infra done; app not yet wired to DB.**

Done and on `main` (public: github.com/machadojoy/case-pilot):
- Monorepo (`apps/` + `packages/`), single git repo, MIT license, README.
- `apps/api`: uv + Python 3.14, minimal FastAPI app with `/health`, pytest (1 test),
  ruff + ty configured and clean; pre-commit hooks installed.
- Multi-stage non-root Dockerfile — builds & runs (verified `/health` 200).
- k8s Deployment (2 replicas) + Service — verified on the `casepilot` k3d cluster.
- **PostgreSQL 17 via docker compose** (`compose.yaml`) — up, healthy, reachable on
  localhost:5432. Decision: Postgres from day one, NOT SQLite (dev/prod parity).

## Next up (the very next step)

Wire the app to the now-running Postgres, in this order, pausing after the migration:
1. `uv add "psycopg[binary]"` — the Postgres driver (psycopg 3).
2. `app/core/config.py` — pydantic-settings `Settings` reading the root `.env`
   (`DATABASE_URL`, `postgresql+psycopg://...`).
3. `app/core/db.py` — SQLModel engine (from `DATABASE_URL`) + a session dependency.
   Smoke-test an actual connection (`SELECT 1`) against the compose Postgres.
4. First model: `User` (id, email unique, hashed_password, full_name, created_at).
5. Wire up Alembic and generate the **first migration**; `alembic upgrade head`.
6. **Pause** so the human inspects the Postgres schema (`docker exec ... psql`).

## Phase 1 checklist

- [x] Scaffolding: monorepo, uv, runnable API, Docker, k8s, tests, pre-commit
- [x] Local PostgreSQL via docker compose (`compose.yaml`, verified healthy)
- [ ] psycopg driver + `core/config.py` (pydantic-settings, reads `.env`)
- [ ] `core/db.py` (engine from DATABASE_URL + session dependency)
- [ ] Alembic set up + first migration (against Postgres)
- [ ] Models: User, Jurisdiction, CaseType, Lawyer (M:N), Dossier
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

## End-of-session ritual

1. Commit + push everything (WIP commits are fine — say "WIP" in the message).
2. Update **Current status**, **Next up**, and check off the checklist here.
3. Leave a breadcrumb above for anything half-done or non-obvious.
