from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
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


def test_create_code_chunk_success(db_session):
    repo = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/example/repo",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.flush()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/main.py",
        size_bytes=500,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.flush()

    chunk = CodeChunk(
        repository_id=repo.id,
        file_id=file_row.id,
        file_path=file_row.path,
        commit_sha="abcdef123456",
        chunk_index=0,
        start_line=1,
        end_line=25,
        content="def hello():\n    return 'world'\n",
        embedding=[0.123, -0.456, 0.789],
    )
    db_session.add(chunk)
    db_session.flush()

    loaded = db_session.get(CodeChunk, chunk.id)
    assert loaded is not None
    assert loaded.repository_id == repo.id
    assert loaded.file_id == file_row.id
    assert loaded.file_path == "src/main.py"
    assert loaded.path == "src/main.py"
    assert loaded.commit_sha == "abcdef123456"
    assert loaded.chunk_index == 0
    assert loaded.start_line == 1
    assert loaded.end_line == 25
    assert loaded.content == "def hello():\n    return 'world'\n"
    assert loaded.embedding == [0.123, -0.456, 0.789]
    assert loaded.created_at is not None


def test_code_chunk_unique_constraint(db_session):
    repo = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/example/repo",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.flush()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/main.py",
        size_bytes=500,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.flush()

    chunk1 = CodeChunk(
        repository_id=repo.id,
        file_id=file_row.id,
        file_path=file_row.path,
        chunk_index=0,
        start_line=1,
        end_line=20,
        content="first chunk",
    )
    db_session.add(chunk1)
    db_session.flush()

    # Attempt inserting duplicate (file_id, chunk_index)
    chunk2 = CodeChunk(
        repository_id=repo.id,
        file_id=file_row.id,
        file_path=file_row.path,
        chunk_index=0,
        start_line=21,
        end_line=40,
        content="duplicate chunk index",
    )
    db_session.add(chunk2)
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_code_chunk_cascade_delete_with_repository(db_session):
    repo = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/example/repo",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.flush()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/main.py",
        size_bytes=500,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.flush()

    chunk = CodeChunk(
        repository_id=repo.id,
        file_id=file_row.id,
        file_path=file_row.path,
        chunk_index=0,
        start_line=1,
        end_line=20,
        content="sample content",
    )
    db_session.add(chunk)
    db_session.flush()
    chunk_id = chunk.id

    # Deleting the repository should cascade delete repository_files and code_chunks in the database
    db_session.delete(repo)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(CodeChunk, chunk_id) is None

