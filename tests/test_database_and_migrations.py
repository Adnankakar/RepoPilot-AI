import subprocess
import sys
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models.user import User, UserRole


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["message"] == "RepoPilot AI"
    assert data["docs"] == "/docs"


def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_database_unique_email_constraint(db_session):
    email = f"unique_{uuid4().hex[:8]}@example.com"
    user1 = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=UserRole.DEVELOPER,
    )
    db_session.add(user1)
    db_session.flush()

    user2 = User(
        email=email,
        password_hash=hash_password("DifferentPassword123!"),
        role=UserRole.DEVELOPER,
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_database_not_null_constraints(db_session):
    # Attempt inserting user without email
    user = User(
        email=None,
        password_hash=hash_password("Password123!"),
        role=UserRole.DEVELOPER,
    )
    db_session.add(user)
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_postgresql_enum_labels(db_session):
    """Verify that PostgreSQL user_role enum labels match Python UserRole values."""
    result = db_session.execute(sa.text("""
        SELECT e.enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'user_role'
        ORDER BY e.enumsortorder;
    """)).fetchall()

    db_enum_labels = [row[0] for row in result]
    expected_labels = [role.value for role in UserRole]

    assert db_enum_labels == expected_labels
    assert "developer" in db_enum_labels
    assert "administrator" in db_enum_labels


def test_alembic_migrations_consistency():
    """Verify that Alembic has no unapplied model-to-schema differences."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Alembic check failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "No new upgrade operations detected" in result.stdout or "No new upgrade operations detected" in result.stderr
