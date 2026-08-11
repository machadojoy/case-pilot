# CasePilot — agent guide

Self-study full-stack project for learning FastAPI, React+TS, gRPC, and system design.
Product + phase roadmap: see `PHASE1.md`.

> **Read `PROGRESS.md` first** — it holds the current status, the next concrete step,
> and handoff notes. This file (`CLAUDE.md`) holds only the stable rules/conventions.

## How the human wants to work

- **One step at a time.** Do a single discrete slice, verify it, commit, then pause —
  don't generate everything at once. The point is to learn, not to ship fast.
- **Explain the "why"** as you go (tradeoffs, mental models). Discuss architecture/tool
  decisions before acting on them.
- **Treat it as if it were production**, even though it's a weekend learning project.
- Prefer **modern, lightweight, well-maintained** tooling; flag stale/deprecated libs.

## Repo layout (monorepo)

```
apps/api/     FastAPI service (the whole backend today)
  app/        application code — feature modules go here
  tests/      pytest
  k8s/        Kubernetes manifests (Deployment + Service)
apps/web/     React frontend (not created yet)
packages/     shared code, incl. future gRPC/proto contracts (Phase 4)
```

## Conventions

- **Module shape:** each backend feature keeps `models.py / schemas.py / router.py /
  service.py` (+ `deps.py` where needed). This is deliberate — it keeps modules
  extraction-ready for the Phase 4 microservice split.
- **FastAPI:** use the `fastapi` skill for conventions (Annotated params/deps, return
  types / response_model, one HTTP op per function, router-level prefix/tags).
- **DB:** SQLModel (not raw SQLAlchemy) + Alembic migrations, SQLite in dev.
- **Auth:** PyJWT + `pwdlib[bcrypt]`. Do NOT use python-jose or passlib (unmaintained).
- **Python:** managed by `uv`, pinned to 3.14. Add deps with `uv add` (runtime) /
  `uv add --dev` (tooling). Never hand-edit the venv.
- Commit in small, atomic, well-described steps. Push at end of session.

## Commands (run from `apps/api/`)

```bash
uv run fastapi dev        # dev server -> http://localhost:8000 (/docs)
uv run pytest             # tests
uv run ruff check .       # lint   (uv run ruff format . to format)
uv run ty check           # type-check
```

Docker / k8s workflows: see `README.md`. Local cluster name: `casepilot`.
Container engine is **Colima** (`colima start`); local k8s is **k3d**.

## Definition of done for a step

Code + a test where it makes sense; `ruff` and `ty` clean; verified it actually runs;
committed. Then update `PROGRESS.md` and pause.
