import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.db import SessionDep
from app.organizations import service
from app.organizations.models import Organization
from app.organizations.schemas import OrganizationCreate, OrganizationPublic

router = APIRouter(prefix="/organizations", tags=["organizations"])


# `def`, not `async def`: psycopg and SQLModel are synchronous, so FastAPI runs
# these in a threadpool. Marking them async would block the event loop on every
# query. Same applies to every DB-touching path operation in this codebase.
@router.post("", response_model=OrganizationPublic, status_code=status.HTTP_201_CREATED)
def create_organization(data: OrganizationCreate, session: SessionDep) -> Organization:
    """Register a new law firm (tenant)."""
    try:
        organization = service.create_organization(session, data)
    except service.SlugUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not derive a free slug for that name.",
        ) from None
    # The router owns the transaction boundary; services only stage their work.
    # When signup grows to Organization + User + Membership, they all land here
    # under one commit.
    session.commit()
    session.refresh(organization)  # load DB-side defaults (timestamps) for the response
    return organization


@router.get("/{organization_id}", response_model=OrganizationPublic)
def get_organization(organization_id: uuid.UUID, session: SessionDep) -> Organization:
    """Fetch a single firm by id."""
    organization = service.get_organization(session, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return organization
