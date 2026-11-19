"""
indexing_worker.py

PostgreSQL-backed background worker for repository indexing jobs.

Claim strategy
--------------
Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple concurrent workers
(or FastAPI BackgroundTasks threads) never process the same job twice.

Retry & Idempotency strategy
----------------------------
- MAX_ATTEMPTS = 3.
- Exponential backoff with random jitter for temporary/transient failures.
- Permanent failures (404, empty repository, auth denied, malformed URL, git missing)
  are never retried — marked failed immediately to conserve resources.
- Safe error summary sanitization strips credentials, secrets, and auth tokens.
- Stale/crashed worker recovery: identifies jobs stuck in 'running' state and resets
  or fails them safely.
- All pipeline stages run with timeouts on external network/subprocess calls.

Testability
-----------
Every helper that opens a session accepts an optional `session_factory`
argument (default: `SessionLocal`).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.services.embedding_provider import EmbeddingProvider, get_embedding_provider
from app.services.indexing_service import (
    PipelineError,
    is_permanent_error,
    run_pipeline,
    sanitize_error_summary,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

SessionFactory = Callable[[], Session]


def _get_embedding_provider() -> EmbeddingProvider | None:
    """Return the shared embedding provider, or None if it cannot initialize.

    Embedding is best-effort enrichment: if the provider cannot be acquired we
    disable embedding for this job (run_pipeline skips the embed stage when the
    provider is None) instead of failing the whole indexing job. The shared
    factory caches a single provider instance and the underlying model is loaded
    once per process, so this never triggers duplicate model loading.
    """
    try:
        return get_embedding_provider()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not initialize embedding provider; embeddings will be "
            "skipped: %s",
            exc,
        )
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay with random jitter for temporary failures:
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    jitter adds between 50% and 100% full-jitter randomness.
    """
    exp_delay = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    if jitter:
        return random.uniform(exp_delay * 0.5, exp_delay)
    return exp_delay


# ---------------------------------------------------------------------------
# Internal helpers — each owns a minimal session scope
# ---------------------------------------------------------------------------

def _get_job_info(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
) -> tuple[str, int] | None:
    """Return (repository_id, attempt_count) or None if not found."""
    db = session_factory()
    try:
        job = db.get(IndexingJob, job_id)
        if job is None:
            return None
        return job.repository_id, job.attempt_count
    finally:
        db.close()


def _claim_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
) -> bool:
    """
    Atomically transition job queued → running using FOR UPDATE SKIP LOCKED.
    Returns False if the job is locked by another worker or not in 'queued' state.
    """
    db = session_factory()
    try:
        stmt = (
            select(IndexingJob)
            .where(
                IndexingJob.id == job_id,
                IndexingJob.status == "queued",
            )
            .with_for_update(skip_locked=True)
        )
        job = db.scalars(stmt).first()
        if job is None:
            return False

        job.status = "running"
        job.started_at = _utc_now()
        job.attempt_count += 1
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def claim_next_queued_job(
    session_factory: SessionFactory = SessionLocal,
) -> str | None:
    """
    Atomically claim the next queued indexing job using FOR UPDATE SKIP LOCKED.
    Transitions status queued → running, sets started_at, increments attempt_count.
    Returns the claimed job_id, or None if no queued job is available.
    """
    db = session_factory()
    try:
        stmt = (
            select(IndexingJob)
            .where(IndexingJob.status == "queued")
            .order_by(IndexingJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.scalars(stmt).first()
        if job is None:
            return None

        job.status = "running"
        job.started_at = _utc_now()
        job.attempt_count += 1
        job_id = job.id
        db.commit()
        return job_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_completed(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
) -> None:
    db = session_factory()
    try:
        job = db.get(IndexingJob, job_id)
        if job:
            job.status = "completed"
            job.finished_at = _utc_now()
            job.error_summary = None
            job.failed_stage = None
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_failed(
    job_id: str,
    stage: str,
    summary: str,
    session_factory: SessionFactory = SessionLocal,
) -> None:
    db = session_factory()
    try:
        job = db.get(IndexingJob, job_id)
        if job:
            job.status = "failed"
            job.finished_at = _utc_now()
            job.failed_stage = stage
            job.error_summary = sanitize_error_summary(summary)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _requeue(
    job_id: str,
    stage: str | None = None,
    summary: str | None = None,
    session_factory: SessionFactory = SessionLocal,
) -> None:
    db = session_factory()
    try:
        job = db.get(IndexingJob, job_id)
        if job:
            job.status = "queued"
            job.started_at = None
            if stage:
                job.failed_stage = stage
            if summary:
                job.error_summary = sanitize_error_summary(summary)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _update_repository_status(
    repository_id: str,
    status: str,
    session_factory: SessionFactory = SessionLocal,
) -> None:
    db = session_factory()
    try:
        repo = db.get(Repository, repository_id)
        if repo:
            repo.status = status
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Crash Recovery
# ---------------------------------------------------------------------------

def recover_stuck_jobs(
    session_factory: SessionFactory = SessionLocal,
    timeout_seconds: int = 1800,
) -> list[str]:
    """
    Recover jobs left in 'running' state after a worker crash, reboot, or timeout.
    - If attempt_count < MAX_ATTEMPTS: resets to 'queued' for retry.
    - If attempt_count >= MAX_ATTEMPTS: marks permanently as 'failed'.
    Returns list of recovered job IDs.
    """
    db = session_factory()
    recovered_ids: list[str] = []
    try:
        cutoff = _utc_now() - timedelta(seconds=timeout_seconds)
        stmt = (
            select(IndexingJob)
            .where(
                IndexingJob.status == "running",
                or_(
                    IndexingJob.started_at.is_(None),
                    IndexingJob.started_at < cutoff,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        stuck_jobs = list(db.scalars(stmt).all())
        for job in stuck_jobs:
            recovered_ids.append(job.id)
            if job.attempt_count < MAX_ATTEMPTS:
                logger.warning(
                    "Recovering stuck job %s (attempt %d/%d) → requeued.",
                    job.id, job.attempt_count, MAX_ATTEMPTS,
                )
                job.status = "queued"
                job.started_at = None
                job.failed_stage = "crash_recovery"
                job.error_summary = sanitize_error_summary(
                    f"Recovered after running for >{timeout_seconds}s without heartbeat (worker crash)"
                )
            else:
                logger.error(
                    "Stuck job %s exhausted max attempts (%d/%d) → marked failed.",
                    job.id, job.attempt_count, MAX_ATTEMPTS,
                )
                job.status = "failed"
                job.finished_at = _utc_now()
                job.failed_stage = "timeout"
                job.error_summary = sanitize_error_summary(
                    f"Job exceeded execution timeout of {timeout_seconds}s and reached maximum attempts"
                )
                repo = db.get(Repository, job.repository_id)
                if repo:
                    repo.status = "failed"

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return recovered_ids


# ---------------------------------------------------------------------------
# Execution Pipeline
# ---------------------------------------------------------------------------

def _execute_claimed_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    sleep_func: Callable[[float], None] | None = None,
) -> None:
    """Execute the ingestion pipeline for an already-claimed running job."""
    info = _get_job_info(job_id, session_factory)
    if info is None:
        logger.error("_execute_claimed_job: job %s not found", job_id)
        return

    repository_id, attempts_used = info

    logger.info(
        "Job %s claimed — starting pipeline (attempt %d/%d).",
        job_id, attempts_used, MAX_ATTEMPTS,
    )

    try:
        db = session_factory()
        try:
            repo = db.get(Repository, repository_id)
            if repo is None:
                raise PipelineError("setup", f"Repository {repository_id} not found", is_permanent=True)

            # Embeddings run as a best-effort final stage of run_pipeline, after
            # the chunks have been flushed. Passing the provider enables it;
            # None (e.g. if the provider could not be initialized) skips it.
            # run_pipeline isolates embedding failures in a savepoint so they
            # never fail the indexing job.
            discovery = run_pipeline(
                db, repo, embedding_provider=_get_embedding_provider()
            )
            repo.status = "partial" if discovery.stop_reason else "completed"
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        _mark_completed(job_id, session_factory)
        logger.info("Job %s completed successfully.", job_id)

    except PipelineError as exc:
        stage = exc.stage
        summary = str(exc)
        safe_summary = sanitize_error_summary(summary)
        permanent = is_permanent_error(exc)

        logger.warning(
            "Job %s failed at stage '%s' (permanent=%s): %s",
            job_id, stage, permanent, safe_summary,
        )

        info2 = _get_job_info(job_id, session_factory)
        current_attempts = info2[1] if info2 else MAX_ATTEMPTS

        if permanent:
            logger.error(
                "Job %s permanently failed at stage '%s': non-retryable failure.",
                job_id, stage,
            )
            _mark_failed(job_id, stage, safe_summary, session_factory)
            _update_repository_status(repository_id, "failed", session_factory)
        elif current_attempts < MAX_ATTEMPTS:
            delay = calculate_backoff(current_attempts)
            logger.info(
                "Job %s requeued (%d/%d attempts used, backoff=%.2fs).",
                job_id, current_attempts, MAX_ATTEMPTS, delay,
            )
            _requeue(job_id, stage=stage, summary=safe_summary, session_factory=session_factory)
            if sleep_func is not None:
                sleep_func(delay)
        else:
            logger.error(
                "Job %s permanently failed after exhausting %d attempts.",
                job_id, current_attempts,
            )
            _mark_failed(job_id, stage, safe_summary, session_factory)
            _update_repository_status(repository_id, "failed", session_factory)

    except Exception as exc:
        summary = f"Unexpected error: {exc}"
        safe_summary = sanitize_error_summary(summary)
        permanent = is_permanent_error(exc)
        logger.exception("Job %s raised an unexpected error.", job_id)

        info2 = _get_job_info(job_id, session_factory)
        current_attempts = info2[1] if info2 else MAX_ATTEMPTS

        if permanent:
            _mark_failed(job_id, "unknown", safe_summary, session_factory)
            _update_repository_status(repository_id, "failed", session_factory)
        elif current_attempts < MAX_ATTEMPTS:
            delay = calculate_backoff(current_attempts)
            _requeue(job_id, stage="unknown", summary=safe_summary, session_factory=session_factory)
            if sleep_func is not None:
                sleep_func(delay)
        else:
            _mark_failed(job_id, "unknown", safe_summary, session_factory)
            _update_repository_status(repository_id, "failed", session_factory)


def run_indexing_job(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    sleep_func: Callable[[float], None] | None = None,
) -> None:
    """
    Entry point called by FastAPI BackgroundTasks (and tests).

    Runs the ingestion pipeline up to MAX_ATTEMPTS times before
    permanently marking the job as failed. Permanent failures are
    not retried.
    """
    info = _get_job_info(job_id, session_factory)
    if info is None:
        logger.error("run_indexing_job: job %s not found", job_id)
        return

    repository_id, current_attempts = info

    if current_attempts >= MAX_ATTEMPTS:
        logger.warning(
            "Job %s already exhausted %d/%d attempts — skipping.",
            job_id, current_attempts, MAX_ATTEMPTS,
        )
        return

    claimed = _claim_job(job_id, session_factory)
    if not claimed:
        logger.info("Job %s could not be claimed (already running or completed).", job_id)
        return

    _execute_claimed_job(job_id, session_factory, sleep_func=sleep_func)


def process_next_job(
    session_factory: SessionFactory = SessionLocal,
    sleep_func: Callable[[float], None] | None = None,
) -> bool:
    """
    Claim and process the next queued job from the database using FOR UPDATE SKIP LOCKED.
    Returns True if a job was claimed and executed, False if the queue was empty.
    """
    job_id = claim_next_queued_job(session_factory)
    if job_id is None:
        return False
    _execute_claimed_job(job_id, session_factory, sleep_func=sleep_func)
    return True
