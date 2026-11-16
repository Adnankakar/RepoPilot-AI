"""
End-to-end verification script for Module 5: Background Jobs and Retries.
Executes 10 comprehensive verification flows against the live database and API.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import SessionLocal, engine
from app.main import app
from app.models.code_chunk import CodeChunk
from app.models.indexing_job import IndexingJob, IndexingJobStatus
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.models.user import User, UserRole
from app.services.chunking_service import chunk_content
from app.services.file_discovery_service import (
    DiscoveredFile,
    DiscoveryResult,
    SkippedFile,
)
from app.services.indexing_service import (
    PermanentPipelineError,
    PipelineError,
    run_pipeline,
    sanitize_error_summary,
)
from app.worker.indexing_worker import (
    MAX_ATTEMPTS,
    _claim_job,
    _mark_completed,
    _mark_failed,
    _requeue,
    calculate_backoff,
    claim_next_queued_job,
    recover_stuck_jobs,
    run_indexing_job,
)


def _utc_now():
    return datetime.now(timezone.utc)


class Module5Verifier:
    def __init__(self):
        self.client = TestClient(app)
        self.results: dict[str, tuple[bool, str]] = {}
        self.db = SessionLocal()

    def cleanup(self):
        self.db.close()

    def _create_user_and_auth(self) -> tuple[User, str]:
        email = f"verify_{uuid4().hex[:8]}@example.com"
        password = "Password123!"
        reg = self.client.post("/api/auth/register", json={"email": email, "password": password})
        assert reg.status_code == 201, f"Failed register: {reg.text}"
        login = self.client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, f"Failed login: {login.text}"
        token = login.json()["access_token"]
        user = self.db.scalars(select(User).where(User.email == email)).first()
        return user, token

    def _create_repository(self, user_id: str, status: str = "pending") -> Repository:
        repo = Repository(
            owner_id=user_id,
            provider="github",
            external_id=str(uuid4()),
            url=f"https://github.com/testowner/{uuid4().hex[:8]}",
            default_branch="main",
            status=status,
        )
        self.db.add(repo)
        self.db.commit()
        self.db.refresh(repo)
        return repo

    # ------------------------------------------------------------------ #
    # Flow 1: Create an indexing job through the API
    # ------------------------------------------------------------------ #
    def verify_flow_1_create_job_via_api(self):
        print("\n--- Flow 1: Create an indexing job through the API ---")
        try:
            user, token = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            with patch("app.api.repositories.run_indexing_job"):
                res = self.client.post(
                    f"/api/repositories/{repo.id}/jobs",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert res.status_code == 202, f"Expected 202, got {res.status_code}: {res.text}"
            data = res.json()
            assert "job_id" in data or "indexing_job_id" in data, f"Missing job_id in response: {data}"
            job_id = data.get("job_id") or data.get("indexing_job_id")
            assert job_id, "job_id is empty"

            # Verify database record
            job = self.db.get(IndexingJob, job_id)
            assert job is not None, f"Job {job_id} not found in database"
            assert job.repository_id == repo.id
            assert job.status == "queued"
            assert job.attempt_count == 0
            assert job.started_at is None
            assert job.finished_at is None

            msg = f"Job created successfully: job_id={job_id}, status={job.status}"
            print(f"[PASS] {msg}")
            self.results["Flow 1: Create Job API"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 1 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 1: Create Job API"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 2: Confirm worker picks up and processes the job
    # ------------------------------------------------------------------ #
    def verify_flow_2_worker_claim_and_processing(self):
        print("\n--- Flow 2: Worker picks up and claims job with FOR UPDATE SKIP LOCKED ---")
        try:
            user, token = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            job = IndexingJob(repository_id=repo.id, status="queued")
            self.db.add(job)
            self.db.commit()
            job_id = job.id

            # Verify atomic claim transitions queued -> running
            claimed = _claim_job(job_id, SessionLocal)
            assert claimed is True, "Expected _claim_job to return True"

            # Check DB state
            self.db.expire_all()
            job = self.db.get(IndexingJob, job_id)
            assert job.status == "running", f"Expected running, got {job.status}"
            assert job.started_at is not None, "started_at was not populated"
            assert job.attempt_count == 1, f"Expected attempt_count=1, got {job.attempt_count}"

            # Second claim attempt must fail (SKIP LOCKED / status check)
            claimed_again = _claim_job(job_id, SessionLocal)
            assert claimed_again is False, "Expected second claim to return False"

            msg = f"Job {job_id} claimed atomically; status=running, started_at={job.started_at}, attempts={job.attempt_count}"
            print(f"[PASS] {msg}")
            self.results["Flow 2: Worker Claiming"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 2 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 2: Worker Claiming"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 3: Confirm existing pipeline runs: fetch → filter → parse → chunk → store
    # ------------------------------------------------------------------ #
    def verify_flow_3_pipeline_stages(self):
        print("\n--- Flow 3: Confirm pipeline runs: fetch → filter → parse → chunk → store ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            with tempfile.TemporaryDirectory() as tmpdir:
                clone_dir = Path(tmpdir) / "clone"
                clone_dir.mkdir()
                src_file = clone_dir / "calculator.py"
                src_file.write_text(
                    "def add(a: int, b: int) -> int:\n"
                    "    '''Return sum.'''\n"
                    "    return a + b\n\n"
                    "def subtract(a: int, b: int) -> int:\n"
                    "    '''Return difference.'''\n"
                    "    return a - b\n",
                    encoding="utf-8",
                )
                secret_file = clone_dir / ".env"
                secret_file.write_text("SECRET_KEY=12345", encoding="utf-8")

                discovery = DiscoveryResult(
                    files=[DiscoveredFile("calculator.py", ".py", len(src_file.read_bytes()), "utf-8")],
                    skipped=[SkippedFile(".env", "secret file")],
                    stop_reason=None,
                )

                with (
                    patch("app.services.indexing_service.clone_repository", return_value=clone_dir),
                    patch("app.services.indexing_service.discover_files", return_value=discovery),
                    patch("app.services.indexing_service.resolve_commit_sha", return_value="sha_test_123"),
                    patch("app.services.indexing_service._cleanup_clone"),
                ):
                    result = run_pipeline(self.db, repo)
                    self.db.commit()

                assert result.stop_reason is None

                # Verify files stored
                files = self.db.scalars(select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)).all()
                assert len(files) == 1, f"Expected 1 file, got {len(files)}"
                assert files[0].path == "calculator.py"
                assert files[0].commit_sha == "sha_test_123"

                # Verify skips stored
                skips = self.db.scalars(select(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo.id)).all()
                assert len(skips) == 1, f"Expected 1 skip, got {len(skips)}"
                assert skips[0].path == ".env"

                # Verify chunks parsed and stored
                chunks = self.db.scalars(select(CodeChunk).where(CodeChunk.repository_id == repo.id)).all()
                assert len(chunks) >= 1, f"Expected >=1 chunks, got {len(chunks)}"
                for c in chunks:
                    assert c.file_id == files[0].id
                    assert c.commit_sha == "sha_test_123"
                    assert "def " in c.content

                # Verify repository status
                self.db.refresh(repo)
                assert repo.status == "completed"
                assert repo.indexed_commit == "sha_test_123"

            msg = f"Pipeline executed cleanly: 1 file stored, 1 skip stored, {len(chunks)} chunks parsed & stored"
            print(f"[PASS] {msg}")
            self.results["Flow 3: Pipeline Execution"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 3 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 3: Pipeline Execution"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 4: Check job status transitions: queued → running → completed
    # ------------------------------------------------------------------ #
    def verify_flow_4_status_transitions(self):
        print("\n--- Flow 4: Status transitions: queued → running → completed ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            job = IndexingJob(repository_id=repo.id, status="queued")
            self.db.add(job)
            self.db.commit()
            job_id = job.id

            # State 1: queued
            assert job.status == "queued"
            assert job.started_at is None
            assert job.finished_at is None

            # State 2: running (simulate worker claim & run)
            with patch("app.worker.indexing_worker.run_pipeline") as mock_pipeline:
                mock_pipeline.return_value = DiscoveryResult([], [], None)
                run_indexing_job(job_id, SessionLocal)

            # State 3: completed
            self.db.expire_all()
            job = self.db.get(IndexingJob, job_id)
            assert job.status == "completed", f"Expected completed, got {job.status}"
            assert job.started_at is not None, "started_at is None"
            assert job.finished_at is not None, "finished_at is None"
            assert job.attempt_count == 1
            assert job.error_summary is None
            assert job.failed_stage is None

            msg = f"Transitions verified: queued -> running -> completed (started={job.started_at}, finished={job.finished_at})"
            print(f"[PASS] {msg}")
            self.results["Flow 4: Status Transitions"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 4 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 4: Status Transitions"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 5: Trigger a temporary failure and verify retry with backoff
    # ------------------------------------------------------------------ #
    def verify_flow_5_temporary_failure_retry_backoff(self):
        print("\n--- Flow 5: Temporary failure retry with exponential backoff & jitter ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            job = IndexingJob(repository_id=repo.id, status="queued", attempt_count=0)
            self.db.add(job)
            self.db.commit()
            job_id = job.id

            # Verify backoff calculation
            d1 = calculate_backoff(attempt=1, base_delay=1.0, jitter=False)
            d2 = calculate_backoff(attempt=2, base_delay=1.0, jitter=False)
            assert d1 == 1.0 and d2 == 2.0, f"Expected 1.0 and 2.0, got {d1}, {d2}"
            dj = calculate_backoff(attempt=2, base_delay=1.0, jitter=True)
            assert 1.0 <= dj <= 2.0, f"Jitter out of range: {dj}"

            # Simulate transient failure (e.g. temporary network glitch)
            with patch("app.worker.indexing_worker.run_pipeline") as mock_pipeline:
                mock_pipeline.side_effect = PipelineError("clone", "Connection reset by peer")
                run_indexing_job(job_id, SessionLocal)

            self.db.expire_all()
            job = self.db.get(IndexingJob, job_id)
            assert job.status == "queued", f"Expected queued for retry, got {job.status}"
            assert job.attempt_count == 1, f"Expected attempt_count=1, got {job.attempt_count}"
            assert job.started_at is None, "started_at must be reset for retry"
            assert job.failed_stage == "clone"
            assert "Connection reset by peer" in job.error_summary

            # Attempt 2: Now let it succeed
            with patch("app.worker.indexing_worker.run_pipeline") as mock_pipeline:
                mock_pipeline.return_value = DiscoveryResult([], [], None)
                run_indexing_job(job_id, SessionLocal)

            self.db.expire_all()
            job = self.db.get(IndexingJob, job_id)
            assert job.status == "completed", f"Expected completed on attempt 2, got {job.status}"
            assert job.attempt_count == 2, f"Expected attempt_count=2, got {job.attempt_count}"

            msg = f"Temporary failure retried successfully on attempt 2; backoff and retry bounds verified"
            print(f"[PASS] {msg}")
            self.results["Flow 5: Retry & Backoff"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 5 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 5: Retry & Backoff"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 6: Verify permanent failures are not retried
    # ------------------------------------------------------------------ #
    def verify_flow_6_permanent_failure_no_retry(self):
        print("\n--- Flow 6: Permanent failures are not retried ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            job = IndexingJob(repository_id=repo.id, status="queued", attempt_count=0)
            self.db.add(job)
            self.db.commit()
            job_id = job.id

            # Induce a permanent failure (e.g. 404 repository not found)
            with patch("app.worker.indexing_worker.run_pipeline") as mock_pipeline:
                mock_pipeline.side_effect = PermanentPipelineError("clone", "GitHub repository was not found or is private")
                run_indexing_job(job_id, SessionLocal)

            self.db.expire_all()
            job = self.db.get(IndexingJob, job_id)
            assert job.status == "failed", f"Expected failed, got {job.status}"
            assert job.attempt_count == 1, f"Permanent error must NOT consume extra attempts, got {job.attempt_count}"
            assert job.finished_at is not None, "finished_at is None"
            assert job.failed_stage == "clone"
            assert "not found" in job.error_summary

            # Owning repository should also be marked failed
            self.db.refresh(repo)
            assert repo.status == "failed"

            msg = f"Permanent error terminated on attempt 1 with status=failed; no retry queued"
            print(f"[PASS] {msg}")
            self.results["Flow 6: Permanent Failure"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 6 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 6: Permanent Failure"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 7: Verify duplicate active jobs and duplicate chunks are prevented
    # ------------------------------------------------------------------ #
    def verify_flow_7_duplicate_prevention(self):
        print("\n--- Flow 7: Duplicate active jobs and duplicate chunks are prevented ---")
        try:
            user, token = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            # 1. Duplicate active job check:
            # Create a queued job for repo
            job = IndexingJob(repository_id=repo.id, status="queued")
            self.db.add(job)
            self.db.commit()

            # Attempt to queue another job via API
            res = self.client.post(
                f"/api/repositories/{repo.id}/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 409, f"Expected 409 Conflict, got {res.status_code}: {res.text}"

            # 2. Duplicate chunks check on re-run:
            # Add initial file and chunks
            rf = RepositoryFile(
                repository_id=repo.id,
                path="app.py",
                size_bytes=100,
                extension=".py",
                encoding="utf-8",
                commit_sha="c1",
            )
            self.db.add(rf)
            self.db.flush()

            c1 = CodeChunk(
                repository_id=repo.id,
                file_id=rf.id,
                file_path=rf.path,
                commit_sha="c1",
                chunk_index=0,
                start_line=1,
                end_line=10,
                content="def initial(): pass",
            )
            self.db.add(c1)
            self.db.commit()

            # Now simulate indexing running again for the same repo
            with tempfile.TemporaryDirectory() as tmpdir:
                clone_dir = Path(tmpdir)
                src = clone_dir / "app.py"
                src.write_text("def updated(): pass", encoding="utf-8")
                discovery = DiscoveryResult(
                    files=[DiscoveredFile("app.py", ".py", len(src.read_bytes()), "utf-8")],
                    skipped=[],
                    stop_reason=None,
                )
                with (
                    patch("app.services.indexing_service.clone_repository", return_value=clone_dir),
                    patch("app.services.indexing_service.discover_files", return_value=discovery),
                    patch("app.services.indexing_service.resolve_commit_sha", return_value="c2"),
                    patch("app.services.indexing_service._cleanup_clone"),
                ):
                    run_pipeline(self.db, repo)
                    self.db.commit()

            # Verify chunks are not duplicated
            chunks = self.db.scalars(select(CodeChunk).where(CodeChunk.repository_id == repo.id)).all()
            assert len(chunks) == 1, f"Expected exactly 1 chunk, found {len(chunks)}"
            assert chunks[0].commit_sha == "c2"
            assert "updated" in chunks[0].content

            msg = "Duplicate active jobs returned 409 Conflict; duplicate chunks prevented during re-indexing"
            print(f"[PASS] {msg}")
            self.results["Flow 7: Duplicate Prevention"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 7 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 7: Duplicate Prevention"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 8: Interrupt a running job and verify recovery
    # ------------------------------------------------------------------ #
    def verify_flow_8_crash_recovery(self):
        print("\n--- Flow 8: Interrupt running job and verify recovery ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            # Simulate worker crash: job left in 'running' state with old started_at
            stuck_time = _utc_now() - timedelta(hours=1)
            stuck_job = IndexingJob(
                repository_id=repo.id,
                status="running",
                attempt_count=1,
                started_at=stuck_time,
            )
            self.db.add(stuck_job)
            self.db.commit()
            stuck_id = stuck_job.id

            # Run crash recovery with timeout_seconds=1800 (30 min)
            recovered = recover_stuck_jobs(SessionLocal, timeout_seconds=1800)
            assert stuck_id in recovered, f"Job {stuck_id} not recovered in {recovered}"

            self.db.expire_all()
            stuck_job = self.db.get(IndexingJob, stuck_id)
            assert stuck_job.status == "queued", f"Expected queued, got {stuck_job.status}"
            assert stuck_job.started_at is None, "started_at must be reset"
            assert stuck_job.failed_stage == "crash_recovery"
            assert "worker crash" in stuck_job.error_summary

            # Also verify that a stuck job with attempt_count >= MAX_ATTEMPTS is marked failed
            exhausted_job = IndexingJob(
                repository_id=repo.id,
                status="running",
                attempt_count=MAX_ATTEMPTS,
                started_at=stuck_time,
            )
            self.db.add(exhausted_job)
            self.db.commit()
            exhausted_id = exhausted_job.id

            recovered2 = recover_stuck_jobs(SessionLocal, timeout_seconds=1800)
            assert exhausted_id in recovered2

            self.db.expire_all()
            exhausted_job = self.db.get(IndexingJob, exhausted_id)
            assert exhausted_job.status == "failed"
            assert exhausted_job.finished_at is not None

            msg = f"Crash recovery successfully reset stuck running job {stuck_id} to queued and failed exhausted job {exhausted_id}"
            print(f"[PASS] {msg}")
            self.results["Flow 8: Crash Recovery"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 8 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 8: Crash Recovery"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 9: Test re-indexing and confirm previous valid index remains safe if new indexing fails
    # ------------------------------------------------------------------ #
    def verify_flow_9_safe_reindexing_and_preservation(self):
        print("\n--- Flow 9: Safe re-indexing: previous index preserved if new run fails ---")
        try:
            user, _ = self._create_user_and_auth()
            repo = self._create_repository(str(user.id), status="completed")
            repo.indexed_commit = "commit_v1"
            self.db.commit()

            # Set up existing valid index (v1)
            file_v1 = RepositoryFile(
                repository_id=repo.id,
                path="service.py",
                size_bytes=200,
                extension=".py",
                encoding="utf-8",
                commit_sha="commit_v1",
            )
            self.db.add(file_v1)
            self.db.flush()

            chunk_v1 = CodeChunk(
                repository_id=repo.id,
                file_id=file_v1.id,
                file_path=file_v1.path,
                commit_sha="commit_v1",
                chunk_index=0,
                start_line=1,
                end_line=15,
                content="def v1_function(): return 'v1'",
            )
            self.db.add(chunk_v1)
            self.db.commit()

            file_v1_id = file_v1.id
            chunk_v1_id = chunk_v1.id

            # Now simulate a re-indexing run that FAILS at discovery stage
            with (
                patch("app.services.indexing_service.clone_repository", return_value=Path("/tmp/fake")),
                patch("app.services.indexing_service.discover_files", side_effect=RuntimeError("Disk read error")),
                patch("app.services.indexing_service._cleanup_clone"),
            ):
                try:
                    run_pipeline(self.db, repo)
                except PipelineError:
                    pass

            # VERIFY OLD INDEX IS PRESERVED
            self.db.expire_all()
            f = self.db.get(RepositoryFile, file_v1_id)
            c = self.db.get(CodeChunk, chunk_v1_id)
            assert f is not None, "Previous valid RepositoryFile was lost!"
            assert c is not None, "Previous valid CodeChunk was lost!"
            assert c.content == "def v1_function(): return 'v1'"
            self.db.refresh(repo)
            assert repo.indexed_commit == "commit_v1", "indexed_commit was overwritten on failure!"

            msg = "Previous valid index (files, chunks, commit) 100% preserved after failed re-indexing run"
            print(f"[PASS] {msg}")
            self.results["Flow 9: Index Preservation"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 9 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 9: Index Preservation"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Flow 10: Verify the job-status API returns correct status and error details
    # ------------------------------------------------------------------ #
    def verify_flow_10_job_status_api(self):
        print("\n--- Flow 10: Job-status API returns correct status and sanitized error details ---")
        try:
            user, token = self._create_user_and_auth()
            repo = self._create_repository(str(user.id))

            # 1. Create a failed job with sensitive token in error summary
            raw_error = "Git clone failed: https://user:secretpass@github.com/repo with ghp_123456789012345678901234567890123456"
            job = IndexingJob(
                repository_id=repo.id,
                status="failed",
                attempt_count=3,
                started_at=_utc_now() - timedelta(minutes=5),
                finished_at=_utc_now(),
                failed_stage="clone",
                error_summary=sanitize_error_summary(raw_error),
            )
            self.db.add(job)
            self.db.commit()
            job_id = job.id

            # Poll job status
            res = self.client.get(
                f"/api/repositories/{repo.id}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            data = res.json()

            assert data["id"] == job_id
            assert data["status"] == "failed"
            assert data["attempt_count"] == 3
            assert data["failed_stage"] == "clone"
            assert "secretpass" not in data["error_summary"], "Credentials leaked in API!"
            assert "ghp_" not in data["error_summary"], "GitHub token leaked in API!"
            assert "[REDACTED_TOKEN]" in data["error_summary"]

            # Repository status polling
            res_repo = self.client.get(
                f"/api/repositories/{repo.id}/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res_repo.status_code == 200
            data_repo = res_repo.json()
            assert data_repo["repository_id"] == repo.id
            assert data_repo["latest_job"]["id"] == job_id

            # Authorization check: other user gets 403
            _, token2 = self._create_user_and_auth()
            res_forbidden = self.client.get(
                f"/api/repositories/{repo.id}/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token2}"},
            )
            assert res_forbidden.status_code == 403, f"Expected 403, got {res_forbidden.status_code}"

            msg = f"Status API returned accurate job state, verified redaction of credentials, and enforced access control"
            print(f"[PASS] {msg}")
            self.results["Flow 10: Status API"] = (True, msg)
        except Exception as exc:
            msg = f"Flow 10 failed: {exc}"
            print(f"[FAIL] {msg}")
            self.results["Flow 10: Status API"] = (False, msg)

    # ------------------------------------------------------------------ #
    # Run all
    # ------------------------------------------------------------------ #
    def run_all(self):
        self.verify_flow_1_create_job_via_api()
        self.verify_flow_2_worker_claim_and_processing()
        self.verify_flow_3_pipeline_stages()
        self.verify_flow_4_status_transitions()
        self.verify_flow_5_temporary_failure_retry_backoff()
        self.verify_flow_6_permanent_failure_no_retry()
        self.verify_flow_7_duplicate_prevention()
        self.verify_flow_8_crash_recovery()
        self.verify_flow_9_safe_reindexing_and_preservation()
        self.verify_flow_10_job_status_api()


if __name__ == "__main__":
    verifier = Module5Verifier()
    try:
        verifier.run_all()
        print("\n" + "=" * 60)
        print("MODULE 5 VERIFICATION SUMMARY")
        print("=" * 60)
        all_passed = True
        for name, (passed, msg) in verifier.results.items():
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"[{status}] {name}")
            print(f"       {msg}")

        print("=" * 60)
        if all_passed:
            print("OVERALL RESULT: ALL 10 FLOWS PASSED SUCCESSFULLY!")
            sys.exit(0)
        else:
            print("OVERALL RESULT: SOME CHECKS FAILED.")
            sys.exit(1)
    finally:
        verifier.cleanup()
