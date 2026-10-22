from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.models.user import User, UserRole


def _create_test_user(db_session) -> tuple[User, str]:
    user = User(
        email=f"user_{uuid4().hex[:8]}@example.com",
        password_hash="fakehash",
        role=UserRole.DEVELOPER,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id)
    return user, token


def _create_test_repository(db_session, owner_id: str) -> Repository:
    repo = Repository(
        owner_id=owner_id,
        provider="github",
        external_id=str(uuid4()),
        url=f"https://github.com/owner/{uuid4().hex[:8]}",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.commit()
    return repo


def _create_test_file(db_session, repo_id: str, path: str, size: int = 100) -> RepositoryFile:
    rf = RepositoryFile(
        repository_id=repo_id,
        path=path,
        blob_hash="a1b2c3d4e5f6",
        language="Python",
        size_bytes=size,
        commit_sha="c0ffee",
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(rf)
    db_session.commit()
    return rf


def _create_test_skip(db_session, repo_id: str, path: str, reason: str = "ignored file") -> RepositoryFileSkip:
    skip = RepositoryFileSkip(
        repository_id=repo_id,
        path=path,
        reason=reason,
    )
    db_session.add(skip)
    db_session.commit()
    return skip


# ===========================================================================
# 1. GET /api/repositories/{repository_id}/files
# ===========================================================================

class TestGetRepositoryFiles:

    def test_get_files_success_empty(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(
            f"/api/repositories/{repo.id}/files",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json() == []

    def test_get_files_success_with_items(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        _create_test_file(db_session, repo.id, "app/main.py", 250)
        _create_test_file(db_session, repo.id, "app/config.py", 120)

        res = test_client.get(
            f"/api/repositories/{repo.id}/files",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

        # Verify fields conform to RepositoryFileResponse schema
        first = data[0]
        assert "id" in first
        assert first["repository_id"] == repo.id
        assert first["path"] == "app/config.py"
        assert first["size_bytes"] == 120
        assert first["extension"] == ".py"
        assert first["encoding"] == "utf-8"
        assert first["blob_hash"] == "a1b2c3d4e5f6"
        assert first["language"] == "Python"
        assert first["commit_sha"] == "c0ffee"
        assert "discovered_at" in first

        assert data[1]["path"] == "app/main.py"

    def test_get_files_pagination_limit_and_offset(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        for i in range(5):
            _create_test_file(db_session, repo.id, f"src/file_{i:02d}.py", 10 * i)

        # First page with limit=2
        res1 = test_client.get(
            f"/api/repositories/{repo.id}/files?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1) == 2
        assert data1[0]["path"] == "src/file_00.py"
        assert data1[1]["path"] == "src/file_01.py"

        # Second page with limit=2&offset=2
        res2 = test_client.get(
            f"/api/repositories/{repo.id}/files?limit=2&offset=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2) == 2
        assert data2[0]["path"] == "src/file_02.py"
        assert data2[1]["path"] == "src/file_03.py"

        # Third page with limit=2&offset=4
        res3 = test_client.get(
            f"/api/repositories/{repo.id}/files?limit=2&offset=4",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert len(data3) == 1
        assert data3[0]["path"] == "src/file_04.py"

    def test_get_files_pagination_page_and_page_size(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        for i in range(4):
            _create_test_file(db_session, repo.id, f"src/mod_{i}.py")

        res = test_client.get(
            f"/api/repositories/{repo.id}/files?page=2&page_size=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["path"] == "src/mod_2.py"
        assert data[1]["path"] == "src/mod_3.py"

    def test_get_files_missing_repository(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        missing_repo_id = str(uuid4())

        res = test_client.get(
            f"/api/repositories/{missing_repo_id}/files",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Repository not found."

    def test_get_files_unauthorized_access_no_token(self, test_client, db_session):
        user, _ = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(f"/api/repositories/{repo.id}/files")
        assert res.status_code == 401

    def test_get_files_unauthorized_access_invalid_token(self, test_client, db_session):
        user, _ = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(
            f"/api/repositories/{repo.id}/files",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert res.status_code == 401

    def test_get_files_unauthorized_access_other_user_repository(self, test_client, db_session):
        user_owner, _ = _create_test_user(db_session)
        user_other, other_token = _create_test_user(db_session)

        repo = _create_test_repository(db_session, str(user_owner.id))
        _create_test_file(db_session, repo.id, "secret.py")

        res = test_client.get(
            f"/api/repositories/{repo.id}/files",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Not authorized to access this repository."


# ===========================================================================
# 2. GET /api/repositories/{repository_id}/skips
# ===========================================================================

class TestGetRepositorySkips:

    def test_get_skips_success_empty(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(
            f"/api/repositories/{repo.id}/skips",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json() == []

    def test_get_skips_success_with_items(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        _create_test_skip(db_session, repo.id, ".env", "secret file")
        _create_test_skip(db_session, repo.id, "node_modules/pkg/index.js", "dependency directory")

        res = test_client.get(
            f"/api/repositories/{repo.id}/skips",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

        # Verify fields conform to RepositoryFileSkipResponse schema
        first = data[0]
        assert "id" in first
        assert first["repository_id"] == repo.id
        assert first["path"] == ".env"
        assert first["reason"] == "secret file"
        assert "skipped_at" in first

        assert data[1]["path"] == "node_modules/pkg/index.js"
        assert data[1]["reason"] == "dependency directory"

    def test_get_skips_pagination_limit_and_offset(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        for i in range(5):
            _create_test_skip(db_session, repo.id, f"skipped/item_{i:02d}.txt", f"reason {i}")

        res1 = test_client.get(
            f"/api/repositories/{repo.id}/skips?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1) == 2
        assert data1[0]["path"] == "skipped/item_00.txt"
        assert data1[1]["path"] == "skipped/item_01.txt"

        res2 = test_client.get(
            f"/api/repositories/{repo.id}/skips?limit=2&offset=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2) == 2
        assert data2[0]["path"] == "skipped/item_02.txt"
        assert data2[1]["path"] == "skipped/item_03.txt"

        res3 = test_client.get(
            f"/api/repositories/{repo.id}/skips?limit=2&offset=4",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert len(data3) == 1
        assert data3[0]["path"] == "skipped/item_04.txt"

    def test_get_skips_pagination_page_and_page_size(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))
        for i in range(4):
            _create_test_skip(db_session, repo.id, f"skip_{i}.bin", "binary file")

        res = test_client.get(
            f"/api/repositories/{repo.id}/skips?page=2&page_size=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["path"] == "skip_2.bin"
        assert data[1]["path"] == "skip_3.bin"

    def test_get_skips_missing_repository(self, test_client, db_session):
        user, token = _create_test_user(db_session)
        missing_repo_id = str(uuid4())

        res = test_client.get(
            f"/api/repositories/{missing_repo_id}/skips",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
        assert res.json()["detail"] == "Repository not found."

    def test_get_skips_unauthorized_access_no_token(self, test_client, db_session):
        user, _ = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(f"/api/repositories/{repo.id}/skips")
        assert res.status_code == 401

    def test_get_skips_unauthorized_access_invalid_token(self, test_client, db_session):
        user, _ = _create_test_user(db_session)
        repo = _create_test_repository(db_session, str(user.id))

        res = test_client.get(
            f"/api/repositories/{repo.id}/skips",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert res.status_code == 401

    def test_get_skips_unauthorized_access_other_user_repository(self, test_client, db_session):
        user_owner, _ = _create_test_user(db_session)
        user_other, other_token = _create_test_user(db_session)

        repo = _create_test_repository(db_session, str(user_owner.id))
        _create_test_skip(db_session, repo.id, "secret.key", "secret key")

        res = test_client.get(
            f"/api/repositories/{repo.id}/skips",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Not authorized to access this repository."
