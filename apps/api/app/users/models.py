import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field

from app.core.models import TimestampMixin


class UserStatus(StrEnum):
    """Lifecycle of an identity. See `docs/models/user.md` for the full reasoning.

    Two more values are expected but deliberately unbuilt: `unverified` (signup-first,
    no such flow yet) and `closed` (voluntary closure, ships with that flow). Erasure
    is NOT a status — it destroys the row's contents in place (`erased_at`).
    """

    PENDING = "pending"  # a lead: gave an email at intake, has no credentials
    ACTIVE = "active"  # activated: verified email + password, portal access


class User(TimestampMixin, table=True):
    """One row per human — global, never org-scoped. The identity plane.

    Holds only what is needed to authenticate and address an account, because every
    field here is visible to *every* firm the person deals with. Personal details are
    per-firm attested data and hang off `Dossier`, not this table.
    """

    __tablename__ = "users"
    __table_args__ = (
        # `table=True` disables Pydantic validation, so `User(status="banana")`
        # constructs happily. This CHECK is the ONLY enforcement — generated from
        # UserStatus so the enum stays the single source of truth.
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in UserStatus)),
            name="ck_users_status",
        ),
        # Case-insensitive uniqueness in the database rather than in application
        # code: `Joy@x.com` and `joy@x.com` are one mailbox, and a single code path
        # that forgets to normalise would silently fork the identity.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str
    hashed_password: str | None = None  # null for leads — they cannot log in
    full_name: str | None = None  # display only, unverified; one field, not first/last
    status: str = Field(default=UserStatus.PENDING)

    # Proof of mailbox control. Global, because it anchors account ownership rather
    # than asserting a fact about the person (that kind of proof is per-firm).
    email_verified_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Reject any JWT whose `iat` predates this. Stateless JWT has nothing to
    # invalidate, so this column is what closes the pre-hijacking window on
    # verification (DESIGN.md §5).
    sessions_valid_from: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Erasure, not soft delete: the row survives (a Dossier points here) but its
    # contents are destroyed in place. See `docs/models/user.md`.
    erased_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
