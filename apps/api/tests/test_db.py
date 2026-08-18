"""Tests for the session dependency in `app.core.db`.

These deliberately exercise the *real* engine (the one built from settings) rather
than the test-database engine in conftest: the whole point is to prove the wiring
the app uses at runtime works. Everything here is read-only (`SELECT 1`), so it
never mutates the dev database.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.db import SessionDep, get_session


def test_get_session_yields_a_usable_session_and_releases_it() -> None:
    """The dependency yields a live Session, then closes it when exhausted."""
    gen = get_session()
    session = next(gen)

    assert isinstance(session, Session)
    assert session.exec(select(1)).one() == 1
    # Executing autobegins a transaction, so the session now holds a connection.
    assert session.in_transaction()

    # Exhausting the generator runs the `with` block's exit -> session closed.
    with pytest.raises(StopIteration):
        next(gen)

    assert not session.in_transaction()


def test_session_dep_resolves_in_an_endpoint() -> None:
    """`SessionDep` is injectable: FastAPI resolves it to a working Session."""
    app = FastAPI()

    @app.get("/db-check")
    def db_check(session: SessionDep) -> dict[str, int]:
        return {"result": session.exec(select(1)).one()}

    with TestClient(app) as client:
        response = client.get("/db-check")

    assert response.status_code == 200
    assert response.json() == {"result": 1}
