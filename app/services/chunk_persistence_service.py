"""
chunk_persistence_service.py

Integrates chunk generation with the repository ingestion pipeline and database storage.

Key Responsibilities:
- Generates and persists CodeChunk rows for repository files.
- Stores repository ID, file ID, file path, commit SHA, chunk index, line range, and content.
- Idempotency: prevents duplicate chunks during repeated indexing runs by replacing
  existing chunks for re-indexed files.
- Stale-data cleanup: identifies and purges chunks from older commits.
- Git commit resolution: determines HEAD commit SHA from cloned git repositories.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.services.chunking_service import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_LINES,
    chunk_content,
)

logger = logging.getLogger(__name__)


def resolve_commit_sha(clone_path: str | Path | None) -> str | None:
    """
    Attempt to extract the current HEAD commit SHA from a cloned git repository.
    Returns None if git is unavailable or clone_path is not a valid git repository.
    """
    if clone_path is None:
        return None

    path = Path(clone_path)
    if not path.is_dir():
        return None

    git = shutil.which("git")
    if not git:
        return None

    try:
        result = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha
    except Exception as exc:
        logger.debug("Failed to resolve git commit SHA at %s: %s", path, exc)

    return None


def persist_chunks_for_file(
    db: Session,
    repository_id: str,
    file_id: str,
    file_path: str,
    content: str,
    commit_sha: str | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[CodeChunk]:
    """
    Generate chunks for file content and persist them to the database idempotently.
    Any existing chunks for this file_id are deleted first to prevent duplicate
    chunks or unique constraint violations.
    """
    # 1. Remove existing chunks for this file to ensure idempotency
    db.execute(delete(CodeChunk).where(CodeChunk.file_id == file_id))

    # 2. Generate chunks
    chunks = chunk_content(
        content=content,
        file_path=file_path,
        max_lines=max_lines,
        max_chars=max_chars,
    )

    if not chunks:
        return []

    # 3. Create CodeChunk entities
    created_records: list[CodeChunk] = []
    for c in chunks:
        row = CodeChunk(
            repository_id=repository_id,
            file_id=file_id,
            file_path=file_path,
            commit_sha=commit_sha,
            chunk_index=c.chunk_index,
            start_line=c.start_line,
            end_line=c.end_line,
            content=c.content,
        )
        db.add(row)
        created_records.append(row)

    return created_records


def generate_and_persist_chunks_for_repository(
    db: Session,
    repository_id: str,
    clone_path: str | Path | None = None,
    commit_sha: str | None = None,
    files: list[RepositoryFile] | None = None,
    cleanup_stale: bool = False,
    max_lines: int = DEFAULT_MAX_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> int:
    """
    Iterate over repository files, read content, generate chunks, and persist them.

    Parameters:
        db: Active SQLAlchemy session.
        repository_id: Owning repository ID.
        clone_path: Directory path where repository is cloned on disk.
        commit_sha: Git commit SHA associated with this indexing run.
        files: Optional pre-fetched list of RepositoryFile rows.
        cleanup_stale: If True and commit_sha is provided, removes older commit chunks.
        max_lines: Max lines per chunk.
        max_chars: Max chars per chunk.

    Returns:
        Total number of CodeChunk rows created.
    """
    # Resolve commit SHA from clone if not explicitly passed
    if commit_sha is None and clone_path is not None:
        commit_sha = resolve_commit_sha(clone_path)

    # Fetch files if not provided
    if files is None:
        files = list(
            db.scalars(
                select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
            ).all()
        )

    if not files:
        logger.info("No repository files found to chunk for repository %s", repository_id)
        return 0

    total_chunks = 0
    clone_dir = Path(clone_path) if clone_path is not None else None

    for f in files:
        content: str | None = None
        if clone_dir is not None:
            disk_file = clone_dir / f.path
            if disk_file.is_file():
                try:
                    encoding = f.encoding or "utf-8"
                    content = disk_file.read_text(encoding=encoding, errors="replace")
                except Exception as exc:
                    logger.warning("Could not read file %s for chunking: %s", disk_file, exc)
                    continue

        # If file could not be read or does not exist on disk, skip safely
        if content is None:
            continue

        # Update file's commit_sha if we have one
        if commit_sha is not None and f.commit_sha != commit_sha:
            f.commit_sha = commit_sha

        created = persist_chunks_for_file(
            db=db,
            repository_id=repository_id,
            file_id=f.id,
            file_path=f.path,
            content=content,
            commit_sha=commit_sha,
            max_lines=max_lines,
            max_chars=max_chars,
        )
        total_chunks += len(created)

    # Clean up stale chunks from older commits if requested
    if cleanup_stale and commit_sha is not None:
        cleanup_stale_chunks(db, repository_id, commit_sha)

    # Update repository indexed_commit if available
    if commit_sha is not None:
        repo = db.get(Repository, repository_id)
        if repo and repo.indexed_commit != commit_sha:
            repo.indexed_commit = commit_sha

    logger.info(
        "Persisted %d chunks for repository %s (commit: %s)",
        total_chunks,
        repository_id,
        commit_sha,
    )
    return total_chunks


def get_stale_chunks(
    db: Session,
    repository_id: str,
    current_commit_sha: str,
) -> list[CodeChunk]:
    """
    Find all CodeChunk rows for repository_id that belong to older commits
    (where commit_sha is different from current_commit_sha or is NULL).
    """
    stmt = (
        select(CodeChunk)
        .where(
            CodeChunk.repository_id == repository_id,
            or_(
                CodeChunk.commit_sha != current_commit_sha,
                CodeChunk.commit_sha.is_(None),
            ),
        )
        .order_by(CodeChunk.file_path, CodeChunk.chunk_index)
    )
    return list(db.scalars(stmt).all())


def identify_stale_commits(
    db: Session,
    repository_id: str,
    current_commit_sha: str,
) -> set[str]:
    """
    Return distinct older commit SHAs that still have chunks stored in the database.
    """
    stmt = (
        select(CodeChunk.commit_sha)
        .where(
            CodeChunk.repository_id == repository_id,
            CodeChunk.commit_sha != current_commit_sha,
            CodeChunk.commit_sha.is_not(None),
        )
        .distinct()
    )
    return set(db.scalars(stmt).all())


def cleanup_stale_chunks(
    db: Session,
    repository_id: str,
    current_commit_sha: str,
) -> int:
    """
    Delete all CodeChunk rows for repository_id from older commits.
    Returns the count of deleted chunks.
    """
    stmt = delete(CodeChunk).where(
        CodeChunk.repository_id == repository_id,
        or_(
            CodeChunk.commit_sha != current_commit_sha,
            CodeChunk.commit_sha.is_(None),
        ),
    )
    result = db.execute(stmt)
    count = result.rowcount
    logger.info(
        "Removed %d stale chunks for repository %s (older than %s)",
        count,
        repository_id,
        current_commit_sha,
    )
    return count
