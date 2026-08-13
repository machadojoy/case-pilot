from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from app.core.config import settings

# echo=True prints every SQL statement — great while learning; set False to quiet it.
engine = create_engine(str(settings.database_url), echo=True)


def get_session() -> Generator[Session]:
    """FastAPI dependency: yields a session and guarantees it's closed."""
    with Session(engine) as session:
        yield session


# Reusable dependency alias: write `session: SessionDep` in endpoints instead of
# repeating `Depends(get_session)` everywhere.
SessionDep = Annotated[Session, Depends(get_session)]
