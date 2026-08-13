# CasePilot

A self-study full-stack project for learning **FastAPI**, **React + TypeScript**, **gRPC**,
and **system design** — evolving a modular monolith into microservices across phases.

**Product idea:** a user tells their legal story via chat; a router agent hands off to a
jurisdiction-specific specialist agent (work, housing, family…) that classifies the case
and prepares a dossier.

> **Status:** Phase 1 scaffolding. Runnable API skeleton with a `/health` endpoint,
> containerized and deployable to a local Kubernetes cluster. Feature work (auth, models,
> dossiers, frontend) is next — see [`PHASE1.md`](./PHASE1.md).

## Tech stack

| Layer | Choice |
|-------|--------|
| API | FastAPI + SQLModel + Alembic (Python 3.14, managed by `uv`) |
| Auth | PyJWT + `pwdlib[bcrypt]` |
| Frontend | Vite + React + TypeScript *(coming: `apps/web`)* |
| Tooling | Ruff (lint/format), ty (types), pytest |
| Containers | Docker (via Colima) |
| Kubernetes | k3d (local) |

## Repository layout

This is a **monorepo**. Top-level dirs are the deployable units and shared code:

```
case-pilot/
├── apps/
│   └── api/            # FastAPI service (this is the whole backend today)
│       ├── app/        # application code (main.py, + feature modules later)
│       ├── tests/      # pytest suite
│       ├── k8s/        # Kubernetes manifests (Deployment + Service)
│       └── Dockerfile  # multi-stage, non-root production image
└── packages/           # (later) shared code, e.g. gRPC/proto contracts
```

Planned siblings: `apps/web` (React frontend), `apps/agents` (extracted service, Phase 4).

## Prerequisites (macOS)

Installed via Homebrew:

```bash
brew install uv fnm colima docker docker-compose kubectl k3d
```

- **uv** — Python/dependency manager (downloads its own Python 3.14).
- **fnm** — Node version manager (for the frontend, later).
- **Colima** — Docker engine in a lightweight Linux VM.
- **k3d** — runs a local Kubernetes cluster inside Docker.

## Running the API (local dev)

**1. Start the database** (PostgreSQL, via docker compose — from the repo root):

```bash
cp .env.example .env          # first time only (local dev credentials)
docker compose up -d          # Postgres on localhost:5432
docker compose ps             # confirm it's "healthy"
```

**2. Run the API** (from `apps/api/`):

```bash
cd apps/api
uv run fastapi dev            # http://localhost:8000  (docs at /docs)
curl localhost:8000/health    # -> {"status":"ok"}
```

`uv` auto-creates the virtualenv and installs dependencies on first run.

We use **PostgreSQL from the start** (not SQLite) for dev/prod parity. Stop the DB with
`docker compose down` (keeps data) or `docker compose down -v` (wipes it).

### Tests, lint, types

```bash
cd apps/api
uv run pytest                 # run tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv run ty check               # type-check
```

## Running in Docker

```bash
cd apps/api
colima start                                  # boot the Docker engine (once per session)
docker build -t casepilot-api:0.1.0 .
docker run --rm -p 8000:8000 casepilot-api:0.1.0
curl localhost:8000/health                    # -> {"status":"ok"}
```

## Running on Kubernetes (k3d)

```bash
# 1. Create a local cluster (once)
k3d cluster create casepilot

# 2. Make the local image available to the cluster's isolated containerd
k3d image import casepilot-api:0.1.0 -c casepilot

# 3. Deploy
kubectl apply -f apps/api/k8s/
kubectl rollout status deployment/casepilot-api

# 4. Reach it from your machine
kubectl port-forward svc/casepilot-api 8081:80
curl localhost:8081/health                    # -> {"status":"ok"}
```

Lifecycle helpers:

```bash
k3d cluster stop casepilot      # pause    (resume: k3d cluster start casepilot)
k3d cluster delete casepilot    # tear down
colima stop                     # stop the Docker VM
```

## Roadmap

| Phase | Focus | System-design lesson |
|-------|-------|----------------------|
| **1** | Skeleton + models + auth | Modular monolith, module boundaries |
| 2 | Single classifier agent (Claude tool-use) | Sync vs async processing |
| 3 | Multi-turn chat + SSE streaming | Real-time, stateful vs stateless |
| 4 | Router → specialist hand-off | Extract agents into its own service (gRPC) |
| 5 | Stripe payments (test mode) | Eventual consistency, webhooks, idempotency |
| 6 | Frontend polish + deploy | Solution architecture, observability |

## License

[MIT](./LICENSE) © machadojoy
