from datetime import datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class TimestampMixin(SQLModel):
    """Reusable created_at/updated_at columns (like a Django abstract base model).

    Not a table itself (no `table=True`); concrete models inherit these columns.
    Timestamps are filled by the database (`server_default`) so they're correct
    regardless of how a row is written; `updated_at` bumps on every update.

    Declared with `sa_type` + `sa_column_kwargs` rather than a ready-made
    `sa_column=Column(...)`: SQLModel returns an `sa_column` instance verbatim, and a
    Column belongs to exactly one Table — so a shared one binds to whichever model
    inherits first and the second raises "Column already assigned to Table". Passing
    the recipe instead makes SQLModel build a fresh column per subclass. Concrete
    models, which share nothing, still use plain `sa_column`.
    """

    created_at: datetime | None = Field(
        default=None,
        # ty: SQLModel annotates `sa_type` as `type[Any]`, but a parameterised type
        # *instance* is what SQLAlchemy wants and what SQLModel passes straight to
        # `Column(...)`. The annotation is wrong upstream, not the call.
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": False,
        },
    )
