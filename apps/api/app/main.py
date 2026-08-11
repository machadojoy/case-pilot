from fastapi import FastAPI

app = FastAPI(title="CasePilot API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Kept dependency-free so it works before the DB exists."""
    return {"status": "ok"}
