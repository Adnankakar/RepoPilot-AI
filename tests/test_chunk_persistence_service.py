"""
Tests for app/services/chunk_persistence_service.py

Validates:
- Correct metadata storage (repository_id, file_id, file_path, commit_sha, chunk_index,
  start_line, end_line, content).
- Idempotency: repeated indexing runs do not create duplicate chunks or constraint errors.
- Stale-data detection: identifying older commit chunks for cleanup.
- Stale-data cleanup: removing older commit chunks while preserving active commit chunks.
- Repository ingestion pipeline integration with chunk generation.
"""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.code_chunk import CodeChunk
from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.services.chunk_persistence_service import (
    cleanup_stale_chunks,
    generate_and_persist_chunks_for_repository,
    get_stale_chunks,
    identify_stale_commits,
    persist_chunks_for_file,
    resolve_commit_sha,
)
from app.services.file_discovery_service import DiscoveredFile, DiscoveryResult
from app.services.github_provider import GitHubRepositoryInfo
from app.services.repository_service import register_repository


@pytest.fixture
def repo(db_session):
    r = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/example/repo",
        default_branch="main",
        status="pending",
    )
    db_session.add(r)
    db_session.flush()
    return r


@pytest.fixture
def repo_file(db_session, repo):
    rf = RepositoryFile(
        repository_id=repo.id,
        path="src/math_ops.py",
        size_bytes=120,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(rf)
    db_session.flush()
    return rf


# ===========================================================================
# 1. Metadata Correctness
# ===========================================================================

def test_persist_chunks_for_file_metadata(db_session, repo, repo_file):
    source_code = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def subtract(a, b):\n"
        "    return a - b\n"
    )
    commit_sha = "c0ffee1234567890"

    chunks = persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=repo_file.id,
        file_path=repo_file.path,
        content=source_code,
        commit_sha=commit_sha,
    )
    db_session.flush()

    assert len(chunks) == 2

    # Verify Chunk 0
    c0 = chunks[0]
    assert c0.repository_id == repo.id
    assert c0.file_id == repo_file.id
    assert c0.file_path == "src/math_ops.py"
    assert c0.commit_sha == commit_sha
    assert c0.chunk_index == 0
    assert c0.start_line == 1
    assert c0.end_line == 2
    assert c0.content == "def add(a, b):\n    return a + b"

    # Verify Chunk 1
    c1 = chunks[1]
    assert c1.repository_id == repo.id
    assert c1.file_id == repo_file.id
    assert c1.file_path == "src/math_ops.py"
    assert c1.commit_sha == commit_sha
    assert c1.chunk_index == 1
    assert c1.start_line == 4
    assert c1.end_line == 5
    assert c1.content == "def subtract(a, b):\n    return a - b"

    # Verify database persistence
    db_chunks = list(
        db_session.scalars(
            select(CodeChunk)
            .where(CodeChunk.file_id == repo_file.id)
            .order_by(CodeChunk.chunk_index)
        ).all()
    )
    assert len(db_chunks) == 2
    assert db_chunks[0].id == c0.id
    assert db_chunks[1].id == c1.id


# ===========================================================================
# 2. Idempotency (Prevent Duplicate Chunks on Repeated Runs)
# ===========================================================================

def test_persist_chunks_for_file_idempotency(db_session, repo, repo_file):
    source_code = (
        "def multiply(a, b):\n"
        "    return a * b\n"
    )
    commit_sha = "commit_alpha"

    # Run 1: initial indexing
    chunks_run1 = persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=repo_file.id,
        file_path=repo_file.path,
        content=source_code,
        commit_sha=commit_sha,
    )
    db_session.flush()
    assert len(chunks_run1) == 1

    # Run 2: repeated indexing with identical content
    chunks_run2 = persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=repo_file.id,
        file_path=repo_file.path,
        content=source_code,
        commit_sha=commit_sha,
    )
    db_session.flush()
    assert len(chunks_run2) == 1

    # Query DB to ensure no duplicate chunks exist
    db_chunks = list(
        db_session.scalars(
            select(CodeChunk).where(CodeChunk.file_id == repo_file.id)
        ).all()
    )
    assert len(db_chunks) == 1
    assert db_chunks[0].content == "def multiply(a, b):\n    return a * b"
    assert db_chunks[0].chunk_index == 0


def test_generate_and_persist_chunks_for_repository_idempotency(
    db_session, repo, tmp_path
):
    # Set up disk files
    file1 = tmp_path / "app.py"
    file1.write_text("def run():\n    return 'running'\n", encoding="utf-8")

    file2 = tmp_path / "README.md"
    file2.write_text("# Documentation\nDetails here.\n", encoding="utf-8")

    rf1 = RepositoryFile(
        repository_id=repo.id,
        path="app.py",
        size_bytes=file1.stat().st_size,
        extension=".py",
        encoding="utf-8",
    )
    rf2 = RepositoryFile(
        repository_id=repo.id,
        path="README.md",
        size_bytes=file2.stat().st_size,
        extension=".md",
        encoding="utf-8",
    )
    db_session.add_all([rf1, rf2])
    db_session.flush()

    commit_sha = "commit_100"

    # Run 1
    total1 = generate_and_persist_chunks_for_repository(
        db=db_session,
        repository_id=repo.id,
        clone_path=tmp_path,
        commit_sha=commit_sha,
    )
    db_session.flush()
    assert total1 == 2

    # Run 2 on the same repository and commit
    total2 = generate_and_persist_chunks_for_repository(
        db=db_session,
        repository_id=repo.id,
        clone_path=tmp_path,
        commit_sha=commit_sha,
    )
    db_session.flush()
    assert total2 == 2

    # Total records in DB must still be 2, without duplicate chunks
    total_db_chunks = len(
        list(
            db_session.scalars(
                select(CodeChunk).where(CodeChunk.repository_id == repo.id)
            ).all()
        )
    )
    assert total_db_chunks == 2


# ===========================================================================
# 3. Stale Data Identification and Cleanup
# ===========================================================================

def test_identify_and_cleanup_stale_chunks(db_session, repo, repo_file):
    # Commit 1 chunks
    persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=repo_file.id,
        file_path=repo_file.path,
        content="def v1(): pass\n",
        commit_sha="commit_v1",
    )
    db_session.flush()

    # Second file under Commit 1
    rf2 = RepositoryFile(
        repository_id=repo.id,
        path="src/old_module.py",
        size_bytes=50,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(rf2)
    db_session.flush()

    persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=rf2.id,
        file_path=rf2.path,
        content="def old(): pass\n",
        commit_sha="commit_v1",
    )
    db_session.flush()

    # Commit 2 is now the active commit; re-index rf with new commit
    persist_chunks_for_file(
        db=db_session,
        repository_id=repo.id,
        file_id=repo_file.id,
        file_path=repo_file.path,
        content="def v2(): pass\n",
        commit_sha="commit_v2",
    )
    db_session.flush()

    # Verify stale detection: rf2 still points to commit_v1
    stale_chunks = get_stale_chunks(
        db=db_session,
        repository_id=repo.id,
        current_commit_sha="commit_v2",
    )
    assert len(stale_chunks) == 1
    assert stale_chunks[0].file_id == rf2.id
    assert stale_chunks[0].commit_sha == "commit_v1"

    stale_commits = identify_stale_commits(
        db=db_session,
        repository_id=repo.id,
        current_commit_sha="commit_v2",
    )
    assert stale_commits == {"commit_v1"}

    # Cleanup stale chunks
    deleted_count = cleanup_stale_chunks(
        db=db_session,
        repository_id=repo.id,
        current_commit_sha="commit_v2",
    )
    db_session.flush()
    assert deleted_count == 1

    # Only commit_v2 chunk remains
    remaining = list(
        db_session.scalars(
            select(CodeChunk).where(CodeChunk.repository_id == repo.id)
        ).all()
    )
    assert len(remaining) == 1
    assert remaining[0].commit_sha == "commit_v2"
    assert remaining[0].content == "def v2(): pass"


# ===========================================================================
# 4. Pipeline Integration (register_repository)
# ===========================================================================

def test_register_repository_generates_and_persists_chunks(db_session, tmp_path):
    # Set up disk file in clone dir
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    main_file = src_dir / "main.py"
    main_file.write_text(
        "def entrypoint():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    info = GitHubRepositoryInfo(
        owner="owner",
        name="project",
        url="https://github.com/owner/project",
        default_branch="main",
        latest_commit="sha_commit_abc",
        external_id=str(uuid4()),
    )

    discovery = DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 100, "utf-8")],
        skipped=[],
        stop_reason=None,
    )

    with (
        patch("app.services.repository_service.GitHubProvider") as mock_gh,
        patch("app.services.repository_service.clone_repository", return_value=tmp_path),
        patch("app.services.repository_service.discover_files", return_value=discovery),
    ):
        mock_gh.return_value.get_repository.return_value = info
        repo, job = register_repository(
            db=db_session,
            owner_id=str(uuid4()),
            repo_url="https://github.com/owner/project",
        )

    # Repository & Job state
    assert repo.status == "cloned"
    assert job.status == "cloned"
    assert repo.indexed_commit == "sha_commit_abc"

    # Chunks generated and persisted
    chunks = list(
        db_session.scalars(
            select(CodeChunk).where(CodeChunk.repository_id == repo.id)
        ).all()
    )
    assert len(chunks) == 1

    chunk = chunks[0]
    assert chunk.repository_id == repo.id
    assert chunk.file_path == "src/main.py"
    assert chunk.commit_sha == "sha_commit_abc"
    assert chunk.chunk_index == 0
    assert chunk.start_line == 1
    assert chunk.end_line == 2
    assert chunk.content == "def entrypoint():\n    return 'ok'"
