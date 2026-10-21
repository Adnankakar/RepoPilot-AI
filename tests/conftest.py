import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import engine, get_db
from app.main import app


@pytest.fixture(scope="session")
def client():
    """Unauthenticated client for public endpoints."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    """Isolated database session wrapped in a transaction that always rolls back."""
    connection = engine.connect()
    transaction = connection.begin()
    TestSessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = TestSessionLocal()

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def test_client(db_session):
    """TestClient that uses the isolated transactional db_session."""
    def override_get_db():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
