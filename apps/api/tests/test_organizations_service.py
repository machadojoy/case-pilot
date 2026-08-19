"""Service-level tests, focused on transaction boundaries.

The service must *not* commit. Callers own the transaction so that multi-entity
operations stay atomic — DESIGN.md requires signup to create Organization + owner
User + Membership all-or-nothing.
"""

import pytest
from sqlmodel import select

from app.organizations import service
from app.organizations.models import Organization
from app.organizations.schemas import OrganizationCreate


def test_create_organization_does_not_commit(session):
    """A caller rolling back must undo the organization entirely."""
    organization = service.create_organization(
        session, OrganizationCreate(name="Atomic Firm")
    )
    organization_id = organization.id

    session.rollback()  # stands in for "a later step in the signup failed"

    assert session.get(Organization, organization_id) is None


def _signup_that_fails_after_the_organization(session) -> None:
    """Stand-in for the real signup: Organization, then owner User (which fails)."""
    service.create_organization(session, OrganizationCreate(name="Orphan Firm"))
    raise RuntimeError("could not create the owner User")


def test_failed_later_step_leaves_nothing_behind(session):
    """The orphaned-tenant scenario: org created, then a subsequent step raises."""
    with pytest.raises(RuntimeError):
        _signup_that_fails_after_the_organization(session)

    session.rollback()

    remaining = session.exec(
        select(Organization).where(Organization.slug == "orphan-firm")
    ).first()
    assert remaining is None


def test_slug_collision_still_works_within_one_transaction(session):
    """Savepoint-based retry must not poison the caller's transaction."""
    first = service.create_organization(session, OrganizationCreate(name="Acme Legal"))
    second = service.create_organization(session, OrganizationCreate(name="Acme Legal"))

    assert first.slug == "acme-legal"
    assert second.slug == "acme-legal-2"

    # The surrounding transaction is still healthy: a further write succeeds.
    third = service.create_organization(session, OrganizationCreate(name="Other Firm"))
    assert third.slug == "other-firm"
