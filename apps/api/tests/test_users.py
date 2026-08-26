import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.users.models import User, UserStatus


def test_create_and_read_user(session):
    user = User(
        email="joy@example.com",
        hashed_password="$2b$12$notarealhash",
        full_name="Joy Machado",
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    fetched = session.get(User, user.id)
    assert fetched is not None
    assert fetched.email == "joy@example.com"
    assert fetched.full_name == "Joy Machado"
    assert fetched.status == UserStatus.ACTIVE
    assert fetched.email_verified_at is not None
    assert isinstance(fetched.id, uuid.UUID)  # UUID PK auto-generated
    # timestamps populated by the database on insert
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_lead_defaults_to_pending_without_credentials(session):
    """A lead is minted by email capture alone: no password, no name, unverified."""
    lead = User(email="lead@example.com")
    session.add(lead)
    session.commit()
    session.refresh(lead)

    assert lead.status == UserStatus.PENDING
    assert lead.hashed_password is None
    assert lead.full_name is None
    assert lead.email_verified_at is None
    assert lead.sessions_valid_from is None
    assert lead.erased_at is None


def test_email_is_unique_case_insensitively(session):
    """`Joy@x.com` and `joy@x.com` are one mailbox. The unique index on lower(email)
    is the only thing enforcing that: `table=True` disables Pydantic validation."""
    session.add(User(email="joy@example.com"))
    session.commit()

    session.add(User(email="JOY@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_status_check_constraint_rejects_unknown_value(session):
    """`table=True` disables Pydantic validation: the CHECK is the only enforcement."""
    session.add(User(email="banana@example.com", status="banana"))
    with pytest.raises(IntegrityError):
        session.commit()
