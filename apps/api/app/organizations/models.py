import uuid

from sqlmodel import Field

from app.core.models import TimestampMixin


class Organization(TimestampMixin, table=True):
    """A law-firm workspace — the tenant root everything else scopes to."""

    __tablename__ = "organizations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
