"""
Tests for the background indexing worker and the new job-related API endpoints.

All external I/O (GitHub, git, filesystem) is mocked.
Database interactions use the real db_session fixture (rolling transaction).

Worker functions accept an optional session_factory so tests can pass in a
factory that returns the same transactional db_session instead of opening a
new real connection (which wouldn't see uncommitted test data).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.services.file_discovery_service import (
    DiscoveredFile,
    DiscoveryResult,
    SkippedFile,
)
from app.services.github_provider import GitHubRepositoryInfo
from app.services.indexing_service import (
    PermanentPipelineError,
    PipelineError,
    sanitize_error_summary,
)
from app.worker.indexing_worker import (
    MAX_ATTEMPTS,
    _claim_job,
    _mark_completed,
    _mark_failed,
    _requeue,
    calculate_backoff,
    recover_stuck_jobs,
    run_indexing_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(db, owner_id: str | None = None) -> Repository:
    repo = Repository(
        owner_id=owner_id or str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/testowner/testrepo",
        default_branch="main",
        status="queued",
    )
    db.add(repo)
    db.flush()
    return repo


def _make_job(db, repo: Repository, status: str = "queued", attempt_count: int = 0) -> IndexingJob:
    job = IndexingJob(repository_id=repo.id, status=status, attempt_count=attempt_count)
    db.add(job)
    db.flush()
    return job


def _session_factory(db_session):
    """Return a factory that always yields the same db_session and never closes it."""
    class _NoCloseSession:
        """Wraps db_session to make close() a no-op so the transaction survives."""
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass  # deliberately do nothing — the test owns the session lifecycle

    wrapped = _NoCloseSession(db_session)

    def factory():
        return wrapped

    return factory


def _good_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 100, "utf-8")],
        skipped=[SkippedFile(".env", "secret file")],
        stop_reason=None,
    )


def _partial_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 100, "utf-8")],
        stop_reason="file count limit reached (1 files)",
    )


def _github_info(external_id: str = "999") -> GitHubRepositoryInfo:
    return GitHubRepositoryInfo(
        owner="testowner",
        name="testrepo",
        url="https://github.com/testowner/testrepo",
        default_branch="main",
        latest_commit="abc123",
        external_id=external_id,
    )


# ---------------------------------------------------------------------------
# IndexingJob model — field defaults
# ---------------------------------------------------------------------------

class TestIndexingJobModel:
    def test_default_status_is_queued(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        assert job.status == "queued"

    def test_default_attempt_count_is_zero(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        assert job.attempt_count == 0

    def test_nullable_fields_are_none(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error_summary is None
        assert job.failed_stage is None


# ---------------------------------------------------------------------------
# Worker: _claim_job
# ---------------------------------------------------------------------------

class TestClaimJob:
    def test_claim_transitions_to_running(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        db_session.flush()
        factory = _session_factory(db_session)

        result = _claim_job(job.id, factory)

        assert result is True
        assert job.status == "running"
        assert job.attempt_count == 1
        assert job.started_at is not None

    def test_claim_returns_false_for_running_job(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, status="running")
        db_session.flush()
        factory = _session_factory(db_session)

        assert _claim_job(job.id, factory) is False

    def test_claim_returns_false_for_completed_job(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, status="completed")
        db_session.flush()
        factory = _session_factory(db_session)

        assert _claim_job(job.id, factory) is False

    def test_claim_returns_false_for_nonexistent_job(self, db_session):
        factory = _session_factory(db_session)
        assert _claim_job(str(uuid4()), factory) is False


# ---------------------------------------------------------------------------
# Worker: _mark_completed / _mark_failed / _requeue
# ---------------------------------------------------------------------------

class TestJobStatusHelpers:
    def test_mark_completed(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, status="running")
        db_session.flush()
        factory = _session_factory(db_session)

        _mark_completed(job.id, factory)

        assert job.status == "completed"
        assert job.finished_at is not None
        assert job.error_summary is None

    def test_mark_failed(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, status="running")
        db_session.flush()
        factory = _session_factory(db_session)

        _mark_failed(job.id, "clone", "git exploded", factory)

        assert job.status == "failed"
        assert job.failed_stage == "clone"
        assert "git exploded" in job.error_summary
        assert job.finished_at is not None

    def test_requeue(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, status="running")
        db_session.flush()
        factory = _session_factory(db_session)

        _requeue(job.id, factory)

        assert job.status == "queued"
        assert job.started_at is None


# ---------------------------------------------------------------------------
# Worker: run_indexing_job — success paths
# ---------------------------------------------------------------------------

class TestRunIndexingJobSuccess:
    def test_job_marked_completed_on_success(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        db_session.flush()
        factory = _session_factory(db_session)

        with patch(
            "app.worker.indexing_worker.run_pipeline",
            return_value=_good_discovery(),
        ):
            run_indexing_job(job.id, factory)

        assert job.status == "completed"
        assert repo.status == "completed"

    def test_partial_discovery_sets_partial_status(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        db_session.flush()
        factory = _session_factory(db_session)

        with patch(
            "app.worker.indexing_worker.run_pipeline",
            return_value=_partial_discovery(),
        ):
            run_indexing_job(job.id, factory)

        assert job.status == "completed"
        assert repo.status == "partial"

    def test_attempt_count_incremented(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        db_session.flush()
        factory = _session_factory(db_session)

        with patch(
            "app.worker.indexing_worker.run_pipeline",
            return_value=_good_discovery(),
        ):
            run_indexing_job(job.id, factory)

        assert job.attempt_count == 1


# ---------------------------------------------------------------------------
# Worker: run_indexing_job — failure paths
# ---------------------------------------------------------------------------

class TestRunIndexingJobFailure:
    def test_job_requeued_on_first_failure(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo)
        db_session.flush()
        factory = _session_factory(db_session)

        with patch(
            "app.worker.indexing_worker.run_pipeline",
            side_effect=PipelineError("clone", "git failed"),
        ):
            run_indexing_job(job.id, factory)

        # attempt_count=1 < MAX_ATTEMPTS=3, so job is requeued
        assert job.status == "queued"
        assert job.attempt_count == 1

    def test_job_permanently_failed_after_max_attempts(self, db_session):
        repo = _make_repo(db_session)
        # Pre-set attempt_count so this run exhausts the limit.
        job = _make_job(db_session, repo, attempt_count=MAX_ATTEMPTS - 1)
        db_session.flush()
        factory = _session_factory(db_session)

        with patch(
            "app.worker.indexing_worker.run_pipeline",
            side_effect=PipelineError("chunk", "out of memory"),
        ):
            run_indexing_job(job.id, factory)

        assert job.status == "failed"
        assert job.failed_stage == "chunk"
        assert job.error_summary is not None
        assert repo.status == "failed"

    def test_exhausted_job_is_skipped(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, attempt_count=MAX_ATTEMPTS)
        db_session.flush()
        factory = _session_factory(db_session)

        pipeline_mock = MagicMock()
        with patch("app.worker.indexing_worker.run_pipeline", pipeline_mock):
            run_indexing_job(job.id, factory)

        pipeline_mock.assert_not_called()

    def test_nonexistent_job_does_not_raise(self, db_session):
        factory = _session_factory(db_session)
        # Should log and return cleanly, not raise.
        run_indexing_job(str(uuid4()), factory)

    def test_permanent_failure_not_retried(self, db_session):
        repo = _make_repo(db_session)
        job = _make_job(db_session, repo, attempt_count=0)
        db_session.flush()
        factory = _session_factory(db_session)

        # Permanent error (e.g. 404 or auth failed) should fail immediately on first attempt
        with patch(
            "app.worker.indexing_worker.run_pipeline",
            side_effect=PermanentPipelineError("clone", "repository not found or private"),
        ):
            run_indexing_job(job.id, factory)

        assert job.status == "failed"
        assert job.attempt_count == 1
        assert job.failed_stage == "clone"
        assert repo.status == "failed"

    def test_backoff_calculation(self):
        d1 = calculate_backoff(attempt=1, base_delay=2.0, jitter=False)
        d2 = calculate_backoff(attempt=2, base_delay=2.0, jitter=False)
        d3 = calculate_backoff(attempt=3, base_delay=2.0, jitter=False)

        assert d1 == 2.0
        assert d2 == 4.0
        assert d3 == 8.0

        # Jitter should be within bounds
        dj = calculate_backoff(attempt=2, base_delay=2.0, jitter=True)
        assert 2.0 <= dj <= 4.0

    def test_recover_stuck_jobs(self, db_session):
        repo = _make_repo(db_session)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)

        # 1. Stuck job with attempts < MAX_ATTEMPTS should be requeued
        stuck_job1 = IndexingJob(
            repository_id=repo.id,
            status="running",
            attempt_count=1,
            started_at=old_time,
        )
        # 2. Stuck job with attempts >= MAX_ATTEMPTS should be marked failed
        stuck_job2 = IndexingJob(
            repository_id=repo.id,
            status="running",
            attempt_count=MAX_ATTEMPTS,
            started_at=old_time,
        )
        # 3. Active recent job should NOT be recovered
        active_job = IndexingJob(
            repository_id=repo.id,
            status="running",
            attempt_count=1,
            started_at=datetime.now(timezone.utc),
        )
        db_session.add_all([stuck_job1, stuck_job2, active_job])
        db_session.flush()

        factory = _session_factory(db_session)
        recovered = recover_stuck_jobs(factory, timeout_seconds=1800)

        assert stuck_job1.id in recovered
        assert stuck_job2.id in recovered
        assert active_job.id not in recovered

        assert stuck_job1.status == "queued"
        assert stuck_job1.started_at is None
        assert stuck_job2.status == "failed"
        assert stuck_job2.finished_at is not None

    def test_safe_error_summary_sanitization(self):
        raw = "Error cloning https://user:secret123@github.com/repo with ghp_123456789012345678901234567890123456 and Bearer eyJhbGciOi"
        sanitized = sanitize_error_summary(raw)

        assert "secret123" not in sanitized
        assert "ghp_123456789012345678901234567890123456" not in sanitized
        assert "[REDACTED_TOKEN]" in sanitized
        assert "[REDACTED]" in sanitized
        assert "***:***@" in sanitized

    def test_idempotent_reindexing_and_preserving_old_index(self, db_session, tmp_path):
        from app.models.code_chunk import CodeChunk
        from app.models.repository_file import RepositoryFile
        from app.services.indexing_service import run_pipeline

        repo = _make_repo(db_session)
        clone_dir = tmp_path / "repo_clone"
        clone_dir.mkdir(parents=True)
        py_file = clone_dir / "main.py"
        py_file.write_text("def hello():\n    return 'v1'\n", encoding="utf-8")

        discovery_v1 = DiscoveryResult(
            files=[DiscoveredFile("main.py", ".py", len(py_file.read_bytes()), "utf-8")],
            skipped=[],
            stop_reason=None,
        )

        with (
            patch("app.services.indexing_service.clone_repository", return_value=clone_dir),
            patch("app.services.indexing_service.discover_files", return_value=discovery_v1),
            patch("app.services.indexing_service.resolve_commit_sha", return_value="sha_v1"),
            patch("app.services.indexing_service._cleanup_clone"),
        ):
            run_pipeline(db_session, repo)
            db_session.flush()

        files_v1 = db_session.query(RepositoryFile).filter_by(repository_id=repo.id).all()
        chunks_v1 = db_session.query(CodeChunk).filter_by(repository_id=repo.id).all()
        assert len(files_v1) == 1
        assert len(chunks_v1) >= 1
        assert repo.indexed_commit == "sha_v1"

        # Now simulate a re-indexing run that FAILS at discovery
        with (
            patch("app.services.indexing_service.clone_repository", return_value=clone_dir),
            patch("app.services.indexing_service.discover_files", side_effect=RuntimeError("Transient error")),
            patch("app.services.indexing_service._cleanup_clone"),
        ):
            with pytest.raises(PipelineError):
                run_pipeline(db_session, repo)

        # Verify old index is preserved!
        files_after_fail = db_session.query(RepositoryFile).filter_by(repository_id=repo.id).all()
        chunks_after_fail = db_session.query(CodeChunk).filter_by(repository_id=repo.id).all()
        assert len(files_after_fail) == len(files_v1)
        assert len(chunks_after_fail) == len(chunks_v1)
        assert repo.indexed_commit == "sha_v1"

        # Successful re-indexing run (v2)
        py_file.write_text("def hello():\n    return 'v2'\n", encoding="utf-8")
        discovery_v2 = DiscoveryResult(
            files=[DiscoveredFile("main.py", ".py", len(py_file.read_bytes()), "utf-8")],
            skipped=[],
            stop_reason=None,
        )
        with (
            patch("app.services.indexing_service.clone_repository", return_value=clone_dir),
            patch("app.services.indexing_service.discover_files", return_value=discovery_v2),
            patch("app.services.indexing_service.resolve_commit_sha", return_value="sha_v2"),
            patch("app.services.indexing_service._cleanup_clone"),
        ):
            run_pipeline(db_session, repo)
            db_session.flush()

        # Verify no duplicate chunks exist!
        files_v2 = db_session.query(RepositoryFile).filter_by(repository_id=repo.id).all()
        chunks_v2 = db_session.query(CodeChunk).filter_by(repository_id=repo.id).all()
        assert len(files_v2) == 1
        assert repo.indexed_commit == "sha_v2"
        chunk_indices = [c.chunk_index for c in chunks_v2]
        assert len(chunk_indices) == len(set(chunk_indices))




# ---------------------------------------------------------------------------
# API: POST /repositories  (creates repo + initial queued job)
# ---------------------------------------------------------------------------

class TestCreateRepositoryEndpoint:
    def _register_and_login(self, test_client) -> str:
        email = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        res = test_client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        return res.json()["access_token"]

    def test_returns_201(self, test_client):
        token = self._register_and_login(test_client)
        info = _github_info(str(uuid4()))

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res.status_code == 201

    def test_response_has_indexing_job_id(self, test_client):
        token = self._register_and_login(test_client)
        info = _github_info(str(uuid4()))

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )

        body = res.json()
        assert "indexing_job_id" in body
        assert body["indexing_job_id"]

    def test_initial_status_is_queued(self, test_client):
        token = self._register_and_login(test_client)
        info = _github_info(str(uuid4()))

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res.json()["repository"]["status"] == "queued"


# ---------------------------------------------------------------------------
# API: POST /repositories/{id}/jobs  (trigger indexing — 202)
# ---------------------------------------------------------------------------

class TestTriggerIndexingEndpoint:
    def _register_repo(self, test_client) -> tuple[str, str, str]:
        """Returns (token, repository_id, initial_job_id)."""
        email = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        res = test_client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        token = res.json()["access_token"]

        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            reg = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )
        repo_id = reg.json()["repository"]["id"]
        job_id = reg.json()["indexing_job_id"]
        return token, repo_id, job_id

    def _complete_job(self, test_client, token, repo_id, job_id):
        """Simulate the initial job completing so the repo has no active job."""
        # Drive the job to 'completed' via the worker with a mocked pipeline.
        from app.database import SessionLocal as _SL
        db = _SL()
        try:
            job = db.get(IndexingJob, job_id)
            if job:
                job.status = "completed"
                db.commit()
        finally:
            db.close()

    def test_returns_202(self, test_client):
        token, repo_id, job_id = self._register_repo(test_client)
        self._complete_job(test_client, token, repo_id, job_id)

        with patch("app.api.repositories.run_indexing_job"):
            res = test_client.post(
                f"/api/repositories/{repo_id}/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res.status_code == 202

    def test_response_has_indexing_job_id(self, test_client):
        token, repo_id, job_id = self._register_repo(test_client)
        self._complete_job(test_client, token, repo_id, job_id)

        with patch("app.api.repositories.run_indexing_job"):
            res = test_client.post(
                f"/api/repositories/{repo_id}/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert "indexing_job_id" in res.json()

    def test_conflict_when_job_already_queued(self, test_client):
        token, repo_id, job_id = self._register_repo(test_client)
        self._complete_job(test_client, token, repo_id, job_id)

        with patch("app.api.repositories.run_indexing_job"):
            # First trigger creates a new queued job.
            res1 = test_client.post(
                f"/api/repositories/{repo_id}/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )
            # Second trigger while first is still queued — should conflict.
            res2 = test_client.post(
                f"/api/repositories/{repo_id}/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res1.status_code == 202
        assert res2.status_code == 409

    def test_unauthorized_user_gets_403(self, test_client):
        token, repo_id, job_id = self._register_repo(test_client)
        self._complete_job(test_client, token, repo_id, job_id)

        email2 = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email2, "password": "Password123!"})
        res2 = test_client.post("/api/auth/login", json={"email": email2, "password": "Password123!"})
        other_token = res2.json()["access_token"]

        res = test_client.post(
            f"/api/repositories/{repo_id}/jobs",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert res.status_code == 403

    def test_requires_authentication(self, test_client):
        _, repo_id, _ = self._register_repo(test_client)
        res = test_client.post(f"/api/repositories/{repo_id}/jobs")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# API: GET /repositories/{id}/jobs/{job_id}  (job status polling)
# ---------------------------------------------------------------------------

class TestGetIndexingJobEndpoint:
    def _setup(self, test_client) -> tuple[str, str, str]:
        email = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        res = test_client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        token = res.json()["access_token"]

        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            reg = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )
        return token, reg.json()["repository"]["id"], reg.json()["indexing_job_id"]

    def test_returns_job_status(self, test_client):
        token, repo_id, job_id = self._setup(test_client)
        res = test_client.get(
            f"/api/repositories/{repo_id}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == job_id
        assert body["repository_id"] == repo_id
        assert "status" in body
        assert "attempt_count" in body

    def test_returns_404_for_unknown_job(self, test_client):
        token, repo_id, _ = self._setup(test_client)
        res = test_client.get(
            f"/api/repositories/{repo_id}/jobs/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404

    def test_other_user_cannot_see_job(self, test_client):
        token, repo_id, job_id = self._setup(test_client)

        email2 = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email2, "password": "Password123!"})
        res2 = test_client.post("/api/auth/login", json={"email": email2, "password": "Password123!"})
        other_token = res2.json()["access_token"]

        res = test_client.get(
            f"/api/repositories/{repo_id}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert res.status_code == 403

    def test_requires_authentication(self, test_client):
        _, repo_id, job_id = self._setup(test_client)
        res = test_client.get(f"/api/repositories/{repo_id}/jobs/{job_id}")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# API: GET /repositories/{id}/jobs  (list jobs)
# ---------------------------------------------------------------------------

class TestListIndexingJobsEndpoint:
    def test_returns_list_with_at_least_initial_job(self, test_client):
        email = f"u_{uuid4().hex[:8]}@example.com"
        test_client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        res = test_client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        token = res.json()["access_token"]

        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.worker.indexing_worker.run_pipeline"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            reg = test_client.post(
                "/api/repositories",
                json={"url": "https://github.com/testowner/testrepo"},
                headers={"Authorization": f"Bearer {token}"},
            )
        repo_id = reg.json()["repository"]["id"]

        res = test_client.get(
            f"/api/repositories/{repo_id}/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        jobs = res.json()
        assert isinstance(jobs, list)
        assert len(jobs) >= 1
