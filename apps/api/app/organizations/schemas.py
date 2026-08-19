import uuid
from datetime import datetime

from pydantic import Field
from sqlmodel import SQLModel


class OrganizationCreate(SQLModel):
    """Request body for creating a firm. The slug is derived, never client-supplied."""

    name: str = Field(min_length=1, max_length=200)


class OrganizationPublic(SQLModel):
    """What we expose over HTTP.

    Deliberately separate from the table model: it is the seam that keeps internal
    columns (billing, triage policy, soft-delete flags...) from leaking into
    responses by default as `Organization` grows.
    """

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
