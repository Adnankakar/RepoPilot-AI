"""
indexing_service.py

Encapsulates the full repository ingestion pipeline:
  clone (fetch) → discover (filter) → parse & chunk (staging) → store (atomic swap)

Idempotency & Staging Strategy:
- Generates chunks in memory/staging first.
- Replaces previous repository index records only after all stages succeed
  inside an atomic database transaction.
- If any stage fails, the transaction is rolled back and the previous valid
  index (files, skips, chunks, indexed_commit) is completely preserved.
- Non-retryable errors are classified as PermanentPipelineError so the worker
  does not retry permanent failures.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.repository_security import RepositoryURLValidationError
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.services.chunk_persistence_service import resolve_commit_sha
from app.services.chunking_service import chunk_content
from app.services.clone_service import CloneError, GitNotAvailable, clone_repository
from app.services.file_discovery_service import DiscoveryResult, discover_files
from app.services.github_provider import (
    GitHubRepositoryEmpty,
    GitHubRepositoryNotFound,
)

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when a pipeline stage fails. Carries the stage name and permanent flag."""

    def __init__(
        self,
        stage: str,
        message: str,
        cause: Exception | None = None,
        is_permanent: bool = False,
    ):
        super().__init__(message)
        self.stage = stage
        self.cause = cause
        self.is_permanent = is_permanent


class PermanentPipelineError(PipelineError):
    """Raised when an unrecoverable failure occurs that should never be retried."""

    def __init__(self, stage: str, message: str, cause: Exception | None = None):
        super().__init__(stage, message, cause=cause, is_permanent=True)


def is_permanent_error(exc: Exception) -> bool:
    """Determine whether an exception represents a fatal, non-retryable failure."""
    if isinstance(exc, PermanentPipelineError):
        return True
    if isinstance(exc, (GitHubRepositoryNotFound, GitHubRepositoryEmpty, RepositoryURLValidationError, GitNotAvailable)):
        return True

    if isinstance(exc, PipelineError):
        if getattr(exc, "is_permanent", False):
            return True
        if exc.cause is not None and is_permanent_error(exc.cause):
            return True
        msg = str(exc).lower()
        permanent_terms = (
            "not found",
            "not public",
            "empty",
            "authentication failed",
            "credentials are not allowed",
            "invalid repository",
            "permission denied",
            "could not read username",
            "bad credentials",
            "repository does not exist",
        )
        if any(term in msg for term in permanent_terms):
            return True

    msg = str(exc).lower()
    if any(term in msg for term in ("not found", "authentication failed", "permission denied", "bad credentials")):
        return True

    return False


def sanitize_error_summary(error: str | Exception, max_length: int = 1000) -> str:
    """
    Produce a sanitized, safe error summary:
    - Strips credentials from URLs (e.g. https://user:pass@host -> https://***:***@host)
    - Strips GitHub tokens and PATs
    - Strips Bearer authorization tokens
    - Normalizes whitespace and truncates to safe length.
    """
    msg = str(error) if error else "Unknown error occurred"

    # Redact URL credentials: https://user:pass@github.com -> https://***:***@github.com
    msg = re.sub(r"(https?://)[^:\s/]+:[^@\s/]+@", r"\1***:***@", msg)
    # Redact GitHub tokens (ghp_..., gho_..., github_pat_...)
    msg = re.sub(r"gh[pousr]_[A-Za-z0-9_]{36,}", "[REDACTED_TOKEN]", msg)
    msg = re.sub(r"github_pat_[A-Za-z0-9_]{80,}", "[REDACTED_TOKEN]", msg)
    # Redact Bearer tokens
    msg = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)

    msg = " ".join(msg.split())
    if len(msg) > max_length:
        msg = msg[: max_length - 3] + "..."

    return msg


def _cleanup_clone(owner_id: str, repository_id: str) -> None:
    clone_dir = Path(settings.clone_base_dir) / owner_id / repository_id
    if clone_dir.exists():
        try:
            shutil.rmtree(clone_dir)
            logger.info("Removed clone directory: %s", clone_dir)
        except OSError as exc:
            logger.warning("Could not remove clone directory %s: %s", clone_dir, exc)


def run_pipeline(db: Session, repository: Repository) -> DiscoveryResult:
    """
    Execute the full ingestion pipeline for *repository* with staging & atomic swap.

    Stages:
      1. clone (fetch)     — git clone to local temporary disk
      2. discover (filter) — walk and filter repository files
      3. chunk (parse)     — parse source code and generate chunks staged in memory
      4. store (atomic)    — atomically replace previous index records in DB

    Guarantees:
      - Idempotent: repeated runs produce clean state with no duplicate chunks.
      - Previous valid index is preserved intact if any stage fails.
      - Old index is only replaced upon complete pipeline success.
    """
    owner_id = repository.owner_id
    repo_id = repository.id

    # ------------------------------------------------------------------ #
    # Stage 1: clone (fetch)
    # ------------------------------------------------------------------ #
    try:
        clone_path = clone_repository(
            clone_url=repository.url,
            owner_id=owner_id,
            repository_id=repo_id,
            branch=repository.default_branch,
        )
    except GitNotAvailable as exc:
        raise PermanentPipelineError("clone", str(exc), cause=exc) from exc
    except CloneError as exc:
        msg_lower = str(exc).lower()
        if any(term in msg_lower for term in ("not found", "authentication failed", "could not read username", "repository does not exist")):
            raise PermanentPipelineError("clone", str(exc), cause=exc) from exc
        raise PipelineError("clone", str(exc), cause=exc) from exc
    except Exception as exc:
        raise PipelineError("clone", str(exc), cause=exc) from exc

    # ------------------------------------------------------------------ #
    # Stage 2: discover (filter)
    # ------------------------------------------------------------------ #
    try:
        commit_sha = resolve_commit_sha(clone_path)
        discovery = discover_files(clone_path)
    except Exception as exc:
        _cleanup_clone(owner_id, repo_id)
        raise PipelineError("discover", str(exc), cause=exc) from exc

    # ------------------------------------------------------------------ #
    # Stage 3: parse & chunk (stage in memory before touching DB)
    # ------------------------------------------------------------------ #
    staged_chunks_by_path: dict[str, list] = {}
    clone_dir = Path(clone_path)

    try:
        for f in discovery.files:
            disk_file = clone_dir / f.relative_path
            if not disk_file.is_file():
                continue
            encoding = f.encoding or "utf-8"
            content = disk_file.read_text(encoding=encoding, errors="replace")
            chunks = chunk_content(
                content=content,
                file_path=f.relative_path,
            )
            staged_chunks_by_path[f.relative_path] = chunks
    except Exception as exc:
        _cleanup_clone(owner_id, repo_id)
        raise PipelineError("chunk", str(exc), cause=exc) from exc

    # ------------------------------------------------------------------ #
    # Stage 4: store (atomic swap — replace old index only on success)
    # ------------------------------------------------------------------ #
    try:
        # Atomic replacement: delete existing index records for this repository
        db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repo_id))
        db.execute(delete(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo_id))
        db.execute(delete(RepositoryFile).where(RepositoryFile.repository_id == repo_id))

        # Insert new file records
        path_to_file_id: dict[str, str] = {}
        for f in discovery.files:
            rf = RepositoryFile(
                repository_id=repo_id,
                path=f.relative_path,
                size_bytes=f.size_bytes,
                extension=f.extension,
                encoding=f.encoding,
                commit_sha=commit_sha,
                blob_hash=None,
                language=None,
            )
            db.add(rf)
            db.flush()
            path_to_file_id[f.relative_path] = rf.id

        # Insert new skip records
        for s in discovery.skipped:
            db.add(
                RepositoryFileSkip(
                    repository_id=repo_id,
                    path=s.relative_path,
                    reason=s.reason,
                )
            )

        # Insert new code chunks
        for rel_path, chunks in staged_chunks_by_path.items():
            file_id = path_to_file_id.get(rel_path)
            if not file_id:
                continue
            for c in chunks:
                db.add(
                    CodeChunk(
                        repository_id=repo_id,
                        file_id=file_id,
                        file_path=rel_path,
                        commit_sha=commit_sha,
                        chunk_index=c.chunk_index,
                        start_line=c.start_line,
                        end_line=c.end_line,
                        content=c.content,
                    )
                )

        if commit_sha:
            repository.indexed_commit = commit_sha

        repository.status = "partial" if discovery.stop_reason else "completed"
        db.flush()

    except Exception as exc:
        db.rollback()
        _cleanup_clone(owner_id, repo_id)
        raise PipelineError("store", str(exc), cause=exc) from exc

    # Cleanup local clone upon successful completion
    _cleanup_clone(owner_id, repo_id)
    return discovery
