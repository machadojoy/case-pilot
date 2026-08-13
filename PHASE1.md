# CasePilot — Phase 1: Skeleton + Models + Auth

> Self-study full-stack project. Goals: learn **FastAPI**, **React + TypeScript**, and
> **system design** (modular monolith → microservices → solution architecture).
> Weekend project. Build a **modular monolith first**; extract the agents layer into its
> own service later (Phase 4) to feel *why* you'd split a monolith.

**Product:** CasePilot — a user tells their legal story via chat to a router agent that
routes to a jurisdiction-specific specialist agent (work, housing, family…), which
classifies the case type and prepares a dossier.

> **⚠️ Deviation from this brief:** we use **PostgreSQL from day one** (docker compose),
> not the SQLite suggested below — for dev/prod parity. See `CLAUDE.md` / `PROGRESS.md`.

---

## Phase 1 goal

A runnable full-stack skeleton. A user can register, log in, and submit a "story" that
gets saved as a **draft dossier** with a manually chosen case type. **No AI yet** (that's
Phase 2). This phase is about clean structure and the FastAPI ↔ React contract.

### In scope
- Modular-monolith backend with clean module boundaries
- SQLModel models + Alembic migrations (SQLite)
- JWT auth (register / login / current user)
- Seed data: jurisdictions, case types, a few lawyers
- Minimal React + TS frontend: login page + "submit story" form + list of my dossiers
- CORS wired so the SPA can call the API

### Out of scope (later phases)
Agents/LLM (P2), chat + SSE (P3), service extraction (P4), payments (P5), Docker/deploy (P6).

---

## Repo structure

```
case-pilot/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, router includes
│   │   ├── core/
│   │   │   ├── config.py          # pydantic-settings
│   │   │   ├── db.py               # engine, session dependency
│   │   │   └── security.py         # password hash, JWT encode/decode
│   │   ├── users/
│   │   │   ├── models.py  schemas.py  router.py  service.py  deps.py
│   │   ├── cases/                  # dossier, casetype, jurisdiction, lawyer
│   │   │   ├── models.py  schemas.py  router.py  service.py
│   │   └── seed.py                 # seed jurisdictions/casetypes/lawyers
│   ├── alembic/                    # migrations
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── .env.example
└── frontend/                       # Vite + React + TS
```

Each backend module keeps the shape `model / schema / router / service` so it's
**extraction-ready** for Phase 4. That discipline *is* the system-design lesson in Phase 1.

---

## Data models (Phase 1 subset)

- **User** — id, email (unique), hashed_password, full_name, created_at
- **Jurisdiction** — id, name (e.g. "Work", "Housing", "Family"), slug
- **CaseType** — id, name, jurisdiction_id (FK)
- **Lawyer** — id, name, email, active; **M:N** with Jurisdiction (link table)
- **Dossier** — id, user_id (FK), title, story (text), case_type_id (FK, nullable in P1),
  status (`draft`/`submitted`, default `draft`), created_at

---

## API endpoints

- `POST /auth/register`, `POST /auth/login` (returns JWT), `GET /auth/me`
- `GET /jurisdictions`, `GET /case-types` (optionally `?jurisdiction_id=`)
- `POST /dossiers` (create draft from story + chosen case type)
- `GET /dossiers` (mine), `GET /dossiers/{id}`

---

## Acceptance criteria (Phase 1 is "done" when)

1. `alembic upgrade head` creates the schema; `python -m app.seed` loads
   jurisdictions/case-types/lawyers.
2. `uvicorn app.main:app --reload` runs; `/docs` shows all endpoints.
3. Register → login → get a JWT → `GET /auth/me` works with the token.
4. Create a dossier (authenticated) and see it in `GET /dossiers`.
5. Frontend: log in, submit a story with a case-type dropdown, see it appear in
   "my dossiers".
6. A short `README.md` explains how to run backend + frontend.

---

## Suggested stack

FastAPI · SQLModel · Alembic · `pydantic-settings` · `python-jose` (JWT) ·
`passlib[bcrypt]` · `uv` or `pip`. Frontend: Vite + React + TS with a tiny typed
`api.ts` fetch wrapper.

---

## Kickoff prompt for Claude Code

> Build Phase 1 of **CasePilot**, a full-stack legal-portal learning project. Create a
> modular-monolith FastAPI backend at `case-pilot/backend/` and a Vite + React +
> TypeScript frontend at `case-pilot/frontend/`. Follow the module shape
> `model / schema / router / service` per feature.
>
> **Backend:** SQLModel + Alembic (SQLite), JWT auth (register/login/me), modules
> `core`, `users`, `cases` (Dossier, CaseType, Jurisdiction, Lawyer with a
> Lawyer↔Jurisdiction M:N link). Endpoints: auth register/login/me, list jurisdictions
> & case-types, create/list/get my dossiers (status defaults to `draft`). A `seed.py`
> to load a few jurisdictions (Work, Housing, Family), case types, and lawyers. CORS
> enabled for the Vite dev server.
>
> **Frontend:** login page, a "submit your story" form with a case-type dropdown, and
> a "my dossiers" list — all hitting the API with a typed fetch client.
>
> No LLM/agents, chat, or payments yet — that's later phases. Finish with a `README.md`
> covering how to run both. Explain your structure choices as you go since I'm learning
> FastAPI and React. Use the `fastapi` skill for conventions.

**Tips when you run it:**
- Say "go phase by phase, backend first, and pause after Alembic + auth so I can run it" —
  otherwise it generates everything at once and you learn less.
- Nudge it to "use the fastapi skill for conventions."

---

## Full roadmap (for context)

| Phase | Focus | System design lesson |
|-------|-------|----------------------|
| **1** | Skeleton + models + auth | Modular monolith, module boundaries |
| **2** | Single classifier agent (Claude tool-use) | Sync vs async processing |
| **3** | Multi-turn chat + SSE streaming | Real-time patterns, stateful vs stateless |
| **4** | Router → specialist hand-off | **Extract agents into its own service** |
| **5** | Stripe payments (test mode) | Eventual consistency, webhooks, idempotency |
| **6** | Frontend polish + Docker deploy | Solution architecture, observability |

**Stack:** FastAPI + SQLModel + Alembic · SQLite→Postgres · Claude API (tool-use + SSE) ·
React + TS (Vite) · Stripe test mode · Docker.
