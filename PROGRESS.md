# Progress

Living status + handoff notes. Update this at the end of every session.
(Stable rules live in `CLAUDE.md`; the full plan is in `PHASE1.md`.)

---

## Current status — updated 2026-08-11

**Phase:** 1 (skeleton + models + auth). **Scaffolding complete; feature work not started.**

Done and on `main` (public: github.com/machadojoy/case-pilot):
- Monorepo (`apps/` + `packages/`), single git repo, MIT license, README.
- `apps/api`: uv + Python 3.14, minimal FastAPI app with `/health`, pytest (1 test),
  ruff + ty configured and clean.
- Multi-stage non-root Dockerfile — builds & runs (verified `/health` 200).
- k8s Deployment (2 replicas) + Service — verified on the `casepilot` k3d cluster.

## Next up (the very next step)

Build the config + database foundation, in this order, pausing after the migration:
1. `app/core/config.py` — pydantic-settings (`Settings`, `.env` loading).
2. `app/core/db.py` — SQLModel engine + a session dependency.
3. First model: `User` (id, email unique, hashed_password, full_name, created_at).
4. Wire up Alembic and generate the **first migration**.
5. **Pause** so the human runs `alembic upgrade head` and inspects the SQLite schema.

## Phase 1 checklist

- [x] Scaffolding: monorepo, uv, runnable API, Docker, k8s, tests, CI-less baseline
- [ ] `core/config.py` (pydantic-settings)
- [ ] `core/db.py` (engine + session dependency)
- [ ] Alembic set up + first migration
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

## End-of-session ritual

1. Commit + push everything (WIP commits are fine — say "WIP" in the message).
2. Update **Current status**, **Next up**, and check off the checklist here.
3. Leave a breadcrumb above for anything half-done or non-obvious.
