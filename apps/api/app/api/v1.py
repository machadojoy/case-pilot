"""Version 1 of the public API.

Feature routers stay version-agnostic — they declare only their own prefix
(`/organizations`). This module is the single place the version lives, so a
future v2 is a new aggregator that re-includes (or forks) feature routers,
not an edit to every module.

Infrastructure routes like `/health` are deliberately NOT mounted here: k8s
probes and the Dockerfile point at the unversioned path.
"""

from fastapi import APIRouter

from app.organizations.router import router as organizations_router

router = APIRouter(prefix="/api/v1")

router.include_router(organizations_router)
