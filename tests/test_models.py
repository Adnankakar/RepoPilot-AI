from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.security import hash_password
from app.models.user import User, UserRole


def test_user_role_enum_values():
    assert UserRole.DEVELOPER == "developer"
    assert UserRole.ADMINISTRATOR == "administrator"
    assert UserRole.DEVELOPER.value == "developer"
    assert UserRole.ADMINISTRATOR.value == "administrator"


def test_user_role_case_insensitivity():
    assert UserRole("developer") == UserRole.DEVELOPER
    assert UserRole("DEVELOPER") == UserRole.DEVELOPER
    assert UserRole("Developer") == UserRole.DEVELOPER
    assert UserRole("administrator") == UserRole.ADMINISTRATOR
    assert UserRole("ADMINISTRATOR") == UserRole.ADMINISTRATOR
    assert UserRole("Administrator") == UserRole.ADMINISTRATOR


def test_sqlalchemy_enum_serialization():
    # Inspect the Enum column configuration on the User model
    role_column = User.__table__.columns["role"]
    enum_type = role_column.type
    assert isinstance(enum_type, sa.Enum)
    assert enum_type.name == "user_role"

    dialect = postgresql.dialect()
    bind_processor = enum_type.bind_processor(dialect)
    result_processor = enum_type.result_processor(dialect, None)

    # Bind processor must serialize to lowercase database enum values
    assert bind_processor(UserRole.DEVELOPER) == "developer"
    assert bind_processor(UserRole.ADMINISTRATOR) == "administrator"

    # Result processor must deserialize database string back to UserRole
    assert result_processor("developer") == UserRole.DEVELOPER
    assert result_processor("administrator") == UserRole.ADMINISTRATOR


def test_create_user_with_developer_role(db_session):
    email = f"dev_{uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=UserRole.DEVELOPER,
    )
    db_session.add(user)
    db_session.flush()

    loaded = db_session.query(User).filter(User.email == email).first()
    assert loaded is not None
    assert loaded.role == UserRole.DEVELOPER
    assert loaded.role.value == "developer"


def test_create_user_with_administrator_role(db_session):
    email = f"admin_{uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=UserRole.ADMINISTRATOR,
    )
    db_session.add(user)
    db_session.flush()

    loaded = db_session.query(User).filter(User.email == email).first()
    assert loaded is not None
    assert loaded.role == UserRole.ADMINISTRATOR
    assert loaded.role.value == "administrator"
