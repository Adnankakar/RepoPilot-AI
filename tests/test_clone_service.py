"""
Tests for app/services/clone_service.py

All git operations are mocked — no network access, no real git invocations.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.clone_service import (
    CloneError,
    GitNotAvailable,
    clone_repository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# GitNotAvailable — git not on PATH
# ---------------------------------------------------------------------------

def test_raises_git_not_available_when_git_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(GitNotAvailable, match="git is not installed"):
        clone_repository(
            clone_url="https://github.com/owner/repo",
            owner_id="user-1",
            repository_id="repo-1",
            branch="main",
        )


# ---------------------------------------------------------------------------
# Successful clone
# ---------------------------------------------------------------------------

def test_returns_dest_path_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", return_value=_make_completed(0)) as mock_run:
        result = clone_repository(
            clone_url="https://github.com/owner/repo",
            owner_id="user-1",
            repository_id="repo-1",
            branch="main",
        )

    expected = tmp_path / "user-1" / "repo-1"
    assert result == expected
    mock_run.assert_called_once()


def test_clone_command_contains_expected_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", return_value=_make_completed(0)) as mock_run:
        clone_repository(
            clone_url="https://github.com/owner/repo",
            owner_id="user-1",
            repository_id="repo-1",
            branch="develop",
        )

    cmd = mock_run.call_args[0][0]
    assert "--depth" in cmd
    assert "1" in cmd
    assert "--single-branch" in cmd
    assert "--branch" in cmd
    assert "develop" in cmd
    assert "https://github.com/owner/repo" in cmd


def test_removes_existing_clone_before_recloning(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    # Pre-create the destination to simulate a stale clone
    dest = tmp_path / "user-1" / "repo-1"
    dest.mkdir(parents=True)
    stale_file = dest / "stale.py"
    stale_file.write_text("old")

    with patch("subprocess.run", return_value=_make_completed(0)):
        clone_repository(
            clone_url="https://github.com/owner/repo",
            owner_id="user-1",
            repository_id="repo-1",
            branch="main",
        )

    # The stale file must be gone (directory was wiped before clone)
    assert not stale_file.exists()


# ---------------------------------------------------------------------------
# CloneError — non-zero exit code
# ---------------------------------------------------------------------------

def test_raises_clone_error_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", return_value=_make_completed(128, stderr="repository not found")):
        with pytest.raises(CloneError, match="exit code 128"):
            clone_repository(
                clone_url="https://github.com/owner/repo",
                owner_id="user-1",
                repository_id="repo-1",
                branch="main",
            )


def test_clone_error_message_includes_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", return_value=_make_completed(128, stderr="fatal: repo not found")):
        with pytest.raises(CloneError, match="fatal: repo not found"):
            clone_repository(
                clone_url="https://github.com/owner/repo",
                owner_id="user-1",
                repository_id="repo-1",
                branch="main",
            )


# ---------------------------------------------------------------------------
# CloneError — timeout
# ---------------------------------------------------------------------------

def test_raises_clone_error_on_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=300)):
        with pytest.raises(CloneError, match="timed out"):
            clone_repository(
                clone_url="https://github.com/owner/repo",
                owner_id="user-1",
                repository_id="repo-1",
                branch="main",
            )


# ---------------------------------------------------------------------------
# CloneError — OS error launching git
# ---------------------------------------------------------------------------

def test_raises_clone_error_on_os_error(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("app.core.config.settings.clone_base_dir", str(tmp_path))

    with patch("subprocess.run", side_effect=OSError("Permission denied")):
        with pytest.raises(CloneError, match="Failed to launch git"):
            clone_repository(
                clone_url="https://github.com/owner/repo",
                owner_id="user-1",
                repository_id="repo-1",
                branch="main",
            )
