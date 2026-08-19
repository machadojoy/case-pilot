from fastapi import FastAPI

from app.api.v1 import router as v1_router

app = FastAPI(title="CasePilot API")

app.include_router(v1_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Kept dependency-free so it works before the DB exists.

    Deliberately unversioned: k8s manifests and the Dockerfile point here.
    """
    return {"status": "ok"}
