"""
Tests for app/services/repository_service.register_repository and
the POST /api/repositories endpoint.

All GitHub API calls, git operations, and filesystem operations are mocked.
No network access. No real git invocations. Uses the real DB via db_session.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.services.clone_service import CloneError, GitNotAvailable
from app.services.file_discovery_service import (
    DiscoveredFile,
    DiscoveryResult,
    SkippedFile,
)
from app.services.github_provider import (
    GitHubProviderUnavailable,
    GitHubRepositoryEmpty,
    GitHubRepositoryInfo,
    GitHubRepositoryNotFound,
)
from app.services.repository_service import (
    RepositoryAlreadyRegistered,
    register_repository,
)
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Shared test doubles
# ---------------------------------------------------------------------------

def _github_info(external_id: str = "999") -> GitHubRepositoryInfo:
    return GitHubRepositoryInfo(
        owner="testowner",
        name="testrepo",
        url="https://github.com/testowner/testrepo",
        default_branch="main",
        latest_commit="abc123",
        external_id=external_id,
    )


def _good_discovery(clone_path: Path | None = None) -> DiscoveryResult:
    return DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 100, "utf-8")],
        skipped=[SkippedFile(".env", "secret file")],
        stop_reason=None,
    )


def _partial_discovery(clone_path: Path | None = None) -> DiscoveryResult:
    return DiscoveryResult(
        files=[DiscoveredFile("src/main.py", ".py", 100, "utf-8")],
        stop_reason="file count limit reached (1 files)",
    )


# ---------------------------------------------------------------------------
# register_repository — success path (status = "cloned")
# ---------------------------------------------------------------------------

class TestRegisterRepositorySuccess:

    def test_returns_repository_and_job(self, db_session, tmp_path):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, job = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert isinstance(repo, Repository)
        assert isinstance(job, IndexingJob)

    def test_status_is_cloned_after_success(self, db_session, tmp_path):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, job = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert repo.status == "cloned"
        assert job.status == "cloned"

    def test_repository_row_persisted(self, db_session, tmp_path):
        info = _github_info(str(uuid4()))
        owner_id = str(uuid4())
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, _ = register_repository(db_session, owner_id, "https://github.com/testowner/testrepo")

        loaded = db_session.get(Repository, repo.id)
        assert loaded is not None
        assert loaded.owner_id == owner_id
        assert loaded.external_id == info.external_id

    def test_file_and_skip_rows_persisted(self, db_session, tmp_path):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, _ = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        files = db_session.scalars(
            select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)
        ).all()
        skips = db_session.scalars(
            select(RepositoryFileSkip).where(RepositoryFileSkip.repository_id == repo.id)
        ).all()
        assert len(files) == 1
        assert len(skips) == 1


# ---------------------------------------------------------------------------
# register_repository — partial status
# ---------------------------------------------------------------------------

class TestRegisterRepositoryPartial:

    def test_status_is_partial_when_discovery_hit_limit(self, db_session, tmp_path):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_partial_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, job = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert repo.status == "partial"
        assert job.status == "partial"


# ---------------------------------------------------------------------------
# register_repository — clone_failed status
# ---------------------------------------------------------------------------

class TestRegisterRepositoryCloneFailed:

    def test_status_is_clone_failed_on_clone_error(self, db_session):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", side_effect=CloneError("git failed")),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, job = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert repo.status == "clone_failed"
        assert job.status == "clone_failed"

    def test_status_is_clone_failed_when_git_not_available(self, db_session):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", side_effect=GitNotAvailable("no git")),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, job = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert repo.status == "clone_failed"
        assert job.status == "clone_failed"

    def test_repository_row_still_persisted_after_clone_failure(self, db_session):
        info = _github_info(str(uuid4()))
        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", side_effect=CloneError("git failed")),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo, _ = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert db_session.get(Repository, repo.id) is not None


# ---------------------------------------------------------------------------
# register_repository — persistence failure cleanup
# ---------------------------------------------------------------------------

class TestRegisterRepositoryPersistenceFailure:

    def test_clone_directory_removed_when_persistence_fails(self, db_session, tmp_path):
        """BUG FIX regression: clone dir must be cleaned up if persistence raises."""
        info = _github_info(str(uuid4()))
        clone_dir = tmp_path / "user-1" / "repo-id"
        clone_dir.mkdir(parents=True)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=clone_dir),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
            patch("app.services.repository_service.persist_discovered_files", side_effect=RuntimeError("db exploded")),
            patch("app.services.repository_service._cleanup_clone") as mock_cleanup,
        ):
            mock_gh.return_value.get_repository.return_value = info
            # db.rollback() inside the service may behave oddly in a nested
            # test transaction; neutralise it so the code path reaches _cleanup_clone
            db_session.rollback = lambda: None
            try:
                register_repository(db_session, "user-1", "https://github.com/testowner/testrepo")
            except Exception:
                pass

        mock_cleanup.assert_called_once()

    def test_status_is_not_cloned_when_persistence_fails(self, db_session, tmp_path):
        """BUG FIX regression: status must not be 'cloned' if persist raises.

        When persist_discovered_files raises, register_repository re-raises
        the exception after setting ingestion_failed and calling _cleanup_clone.
        We verify it raises rather than returning a 'cloned' repository.
        """
        info = _github_info(str(uuid4()))

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
            patch("app.services.repository_service.persist_discovered_files", side_effect=RuntimeError("db exploded")),
            patch("app.services.repository_service._cleanup_clone"),
        ):
            mock_gh.return_value.get_repository.return_value = info
            # The function must raise — it must NOT silently return status="cloned"
            with pytest.raises((RuntimeError, Exception)):
                register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")


# ---------------------------------------------------------------------------
# register_repository — duplicate detection
# ---------------------------------------------------------------------------

class TestRegisterRepositoryDuplicates:

    def test_raises_already_registered_on_second_call(self, db_session, tmp_path):
        external_id = str(uuid4())
        info = _github_info(external_id)
        owner_id = str(uuid4())

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            register_repository(db_session, owner_id, "https://github.com/testowner/testrepo")

            with pytest.raises(RepositoryAlreadyRegistered):
                register_repository(db_session, owner_id, "https://github.com/testowner/testrepo")

    def test_different_users_can_register_same_repo(self, db_session, tmp_path):
        external_id = str(uuid4())
        info = _github_info(external_id)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            repo1, _ = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")
            repo2, _ = register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")

        assert repo1.id != repo2.id


# ---------------------------------------------------------------------------
# register_repository — GitHub provider errors propagate
# ---------------------------------------------------------------------------

class TestRegisterRepositoryGitHubErrors:

    @pytest.mark.parametrize("exc_class", [
        GitHubRepositoryNotFound,
        GitHubRepositoryEmpty,
        GitHubProviderUnavailable,
    ])
    def test_github_error_propagates(self, db_session, exc_class):
        with patch("app.services.repository_service.GitHubProvider") as mock_gh:
            mock_gh.return_value.get_repository.side_effect = exc_class("error")
            with pytest.raises(exc_class):
                register_repository(db_session, str(uuid4()), "https://github.com/testowner/testrepo")


# ---------------------------------------------------------------------------
# POST /api/repositories — API layer ingestion statuses
# ---------------------------------------------------------------------------

class TestRepositoryAPIStatuses:
    """
    Tests for the HTTP layer. Uses test_client fixture (real DB, overridden
    dependency) and mocks GitHub + clone at the service layer.
    """

    def _register_user_and_get_token(self, test_client) -> str:
        email = f"user_{uuid4().hex[:8]}@example.com"
        test_client.post(
            "/api/auth/register",
            json={"email": email, "password": "Password123!"},
        )
        res = test_client.post(
            "/api/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        return res.json()["access_token"]

    def _post_repo(self, test_client, token: str) -> dict:
        return test_client.post(
            "/api/repositories",
            json={"url": "https://github.com/testowner/testrepo"},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_returns_201_with_cloned_status(self, test_client, tmp_path):
        info = _github_info(str(uuid4()))
        token = self._register_user_and_get_token(test_client)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = self._post_repo(test_client, token)

        assert res.status_code == 201
        assert res.json()["repository"]["status"] == "cloned"

    def test_returns_201_with_partial_status(self, test_client, tmp_path):
        info = _github_info(str(uuid4()))
        token = self._register_user_and_get_token(test_client)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_partial_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = self._post_repo(test_client, token)

        assert res.status_code == 201
        assert res.json()["repository"]["status"] == "partial"

    def test_returns_201_with_clone_failed_status(self, test_client):
        info = _github_info(str(uuid4()))
        token = self._register_user_and_get_token(test_client)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", side_effect=CloneError("git failed")),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = self._post_repo(test_client, token)

        assert res.status_code == 201
        assert res.json()["repository"]["status"] == "clone_failed"

    def test_returns_409_on_duplicate_registration(self, test_client, tmp_path):
        external_id = str(uuid4())
        info = _github_info(external_id)
        token = self._register_user_and_get_token(test_client)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            first = self._post_repo(test_client, token)
            assert first.status_code == 201

            second = self._post_repo(test_client, token)
            assert second.status_code == 409

    def test_returns_404_when_github_repo_not_found(self, test_client):
        token = self._register_user_and_get_token(test_client)

        with patch("app.services.repository_service.GitHubProvider") as mock_gh:
            mock_gh.return_value.get_repository.side_effect = GitHubRepositoryNotFound("not found")
            res = self._post_repo(test_client, token)

        assert res.status_code == 404

    def test_returns_502_when_github_unavailable(self, test_client):
        token = self._register_user_and_get_token(test_client)

        with patch("app.services.repository_service.GitHubProvider") as mock_gh:
            mock_gh.return_value.get_repository.side_effect = GitHubProviderUnavailable("rate limited")
            res = self._post_repo(test_client, token)

        assert res.status_code == 502

    def test_returns_401_without_token(self, test_client):
        res = test_client.post(
            "/api/repositories",
            json={"url": "https://github.com/testowner/testrepo"},
        )
        assert res.status_code == 401

    def test_returns_422_for_invalid_url(self, test_client):
        token = self._register_user_and_get_token(test_client)
        res = test_client.post(
            "/api/repositories",
            json={"url": "not-a-url"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 422

    def test_response_contains_indexing_job_id(self, test_client, tmp_path):
        info = _github_info(str(uuid4()))
        token = self._register_user_and_get_token(test_client)

        with (
            patch("app.services.repository_service.GitHubProvider") as mock_gh,
            patch("app.services.repository_service.clone_repository", return_value=tmp_path),
            patch("app.services.repository_service.discover_files", return_value=_good_discovery()),
        ):
            mock_gh.return_value.get_repository.return_value = info
            res = self._post_repo(test_client, token)

        assert "indexing_job_id" in res.json()
        assert res.json()["indexing_job_id"]
