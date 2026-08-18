from datetime import datetime

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel


class TimestampMixin(SQLModel):
    """Reusable created_at/updated_at columns (like a Django abstract base model).

    Not a table itself (no `table=True`); concrete models inherit these columns.
    Timestamps are filled by the database (`server_default`) so they're correct
    regardless of how a row is written; `updated_at` bumps on every update.
    """

    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
