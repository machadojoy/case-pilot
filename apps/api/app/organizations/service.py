import uuid
from collections.abc import Sequence

from slugify import slugify
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.organizations.models import Organization
from app.organizations.schemas import OrganizationCreate

# Safety valve for the retry loop below — reaching it means something pathological
# (thousands of firms with the same name), not normal contention.
MAX_SLUG_ATTEMPTS = 50


class SlugUnavailableError(Exception):
    """Could not find a free slug for this name within MAX_SLUG_ATTEMPTS."""


def create_organization(session: Session, data: OrganizationCreate) -> Organization:
    """Create a firm, deriving a unique slug from its name.

    Collisions resolve by suffixing: `acme-legal`, `acme-legal-2`, ...

    We insert and catch the unique-violation rather than SELECTing first: two
    concurrent requests can both see a slug as free, so a pre-check would still
    let a duplicate through. The database's unique index is the only real arbiter.

    **This function does not commit.** The caller owns the transaction, so that
    multi-entity operations stay atomic — signing up a firm has to create the
    Organization, the owner User and the Membership all-or-nothing (DESIGN.md).
    Committing here would leave an orphaned tenant behind if a later step failed.
    """
    base_slug = slugify(data.name)

    for attempt in range(1, MAX_SLUG_ATTEMPTS + 1):
        slug = base_slug if attempt == 1 else f"{base_slug}-{attempt}"
        organization = Organization(name=data.name, slug=slug)
        try:
            # SAVEPOINT: a unique violation here must roll back only this INSERT.
            # A bare flush + rollback would discard the caller's other work too.
            with session.begin_nested():
                session.add(organization)
                session.flush()  # hits the unique index without committing
        except IntegrityError:
            continue
        return organization

    raise SlugUnavailableError(base_slug)


def get_organization(
    session: Session, organization_id: uuid.UUID
) -> Organization | None:
    """Fetch one firm by id, or None if it doesn't exist."""
    return session.get(Organization, organization_id)


def list_organizations(
    session: Session, *, offset: int, limit: int
) -> tuple[Sequence[Organization], int]:
    """One page of firms, plus the total row count.

    Ordered by `(created_at, id)`. The `id` tiebreaker is not decorative:
    `created_at` defaults to `now()`, which in Postgres is *transaction* time, so
    rows written in the same transaction share it exactly. Without a tiebreaker
    the sort would be non-deterministic and pages could repeat or skip rows.
    """
    total = session.exec(select(func.count()).select_from(Organization)).one()
    items = session.exec(
        select(Organization)
        # col() tells the type checker these are columns, not the plain
        # `datetime | None` / `UUID` values the class-level annotations suggest.
        .order_by(col(Organization.created_at), col(Organization.id))
        .offset(offset)
        .limit(limit)
    ).all()
    return items, total
