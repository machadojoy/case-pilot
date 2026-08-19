from fastapi import FastAPI

from app.organizations.router import router as organizations_router

app = FastAPI(title="CasePilot API")

app.include_router(organizations_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Kept dependency-free so it works before the DB exists."""
    return {"status": "ok"}
