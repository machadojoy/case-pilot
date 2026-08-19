import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel

import app.models  # noqa: F401  (registers all models for create_all)
from app.core.config import settings
from app.core.db import get_session
from app.main import app as fastapi_app  # aliased: bare `app` is the package itself

# Tests run against a dedicated database (casepilot -> casepilot_test) so a test run
# never touches your dev data. Same Postgres server, different database.
_APP_URL = make_url(str(settings.database_url))
_TEST_URL = _APP_URL.set(database=f"{_APP_URL.database}_test")


def _ensure_test_database() -> None:
    """Create the test database if missing (connects to the app DB as admin)."""
    admin_engine = create_engine(_APP_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": _TEST_URL.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_TEST_URL.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def _db_engine():
    _ensure_test_database()
    engine = create_engine(_TEST_URL, echo=False)
    SQLModel.metadata.create_all(engine)  # build schema from the models
    yield engine
    engine.dispose()


@pytest.fixture
def session(_db_engine):
    """A session wrapped in a transaction that is rolled back after each test.

    Each test is fully isolated: whatever it writes (even after commit) is undone,
    so tests can't see each other's data and the DB stays clean.
    """
    connection = _db_engine.connect()
    transaction = connection.begin()
    db_session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db_session
    finally:
        db_session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(session):
    """TestClient whose endpoints share the test's rolled-back session.

    Without the override the app would use the real engine from `app.core.db`,
    so requests made in tests would commit to the database for real and leak
    between tests. Yielding the *same* session keeps API tests inside the
    transaction the `session` fixture rolls back.
    """
    fastapi_app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
