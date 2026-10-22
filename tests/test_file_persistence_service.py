"""
Tests for app/services/file_persistence_service.py

Uses the real db_session fixture (rolls back after each test) and builds
DiscoveryResult objects directly — no git, no network, no disk walking.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.services.file_discovery_service import (
    DiscoveredFile,
    DiscoveryResult,
    SkippedFile,
)
from app.services.file_persistence_service import persist_discovered_files


# ---------------------------------------------------------------------------
# Fixture: a real repository row owned by a generated ID
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(db_session):
    r = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/test/repo",
        default_branch="main",
        status="pending",
    )
    db_session.add(r)
    db_session.flush()
    return r


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

def test_returns_file_count(db_session, repo):
    discovery = DiscoveryResult(
        files=[
            DiscoveredFile("src/a.py", ".py", 10, "utf-8"),
            DiscoveredFile("src/b.py", ".py", 20, "utf-8"),
        ],
        skipped=[SkippedFile(".env", "secret file")],
    )
    count = persist_discovered_files(db_session, repo.id, discovery)
    assert count == 2  # returns accepted file count, not skip count


def test_returns_zero_for_empty_discovery(db_session, repo):
    discovery = DiscoveryResult()
    count = persist_discovered_files(db_session, repo.id, discovery)
    assert count == 0


# ---------------------------------------------------------------------------
# RepositoryFile rows
# ---------------------------------------------------------------------------

def test_inserts_correct_number_of_file_rows(db_session, repo):
    discovery = DiscoveryResult(
        files=[
            DiscoveredFile("src/main.py", ".py", 100, "utf-8"),
            DiscoveredFile("README.md", ".md", 200, "utf-8"),
            DiscoveredFile("Makefile", "", 50, "utf-8"),
        ],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    rows = db_session.scalars(
        select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)
    ).all()
    assert len(rows) == 3


def test_file_row_fields_match_discovered_file(db_session, repo):
    discovery = DiscoveryResult(
        files=[DiscoveredFile("app/utils.py", ".py", 512, "utf-8")],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    row = db_session.scalars(
        select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)
    ).one()
    assert row.path == "app/utils.py"
    assert row.extension == ".py"
    assert row.size_bytes == 512
    assert row.encoding == "utf-8"
    assert row.repository_id == repo.id


def test_nullable_fields_are_none_at_discovery_time(db_session, repo):
    discovery = DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 10, "utf-8")],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    row = db_session.scalars(
        select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)
    ).one()
    assert row.blob_hash is None
    assert row.language is None
    assert row.commit_sha is None


# ---------------------------------------------------------------------------
# RepositoryFileSkip rows
# ---------------------------------------------------------------------------

def test_inserts_correct_number_of_skip_rows(db_session, repo):
    discovery = DiscoveryResult(
        skipped=[
            SkippedFile(".env", "secret file"),
            SkippedFile("node_modules/lodash/index.js", "dependency directory"),
        ],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    rows = db_session.scalars(
        select(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo.id)
    ).all()
    assert len(rows) == 2


def test_skip_row_fields_match_skipped_file(db_session, repo):
    discovery = DiscoveryResult(
        skipped=[SkippedFile("dist/bundle.js", "build output")],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    row = db_session.scalars(
        select(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo.id)
    ).one()
    assert row.path == "dist/bundle.js"
    assert row.reason == "build output"
    assert row.repository_id == repo.id


def test_no_skip_rows_when_nothing_skipped(db_session, repo):
    discovery = DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 10, "utf-8")],
    )
    persist_discovered_files(db_session, repo.id, discovery)
    db_session.flush()

    rows = db_session.scalars(
        select(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo.id)
    ).all()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# No commit — caller controls the transaction
# ---------------------------------------------------------------------------

def test_does_not_commit_session(db_session, repo):
    """persist_discovered_files must not commit; the caller owns the transaction."""
    discovery = DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 10, "utf-8")],
    )
    # Track whether commit was called
    committed = []
    original_commit = db_session.commit
    db_session.commit = lambda: committed.append(True) or original_commit()

    persist_discovered_files(db_session, repo.id, discovery)

    assert committed == [], "persist_discovered_files must not call db.commit()"

    # Restore
    db_session.commit = original_commit
