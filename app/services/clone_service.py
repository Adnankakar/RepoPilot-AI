"""
clone_service.py

Handles cloning a GitHub repository to local disk using git.
Each repository is cloned into a subdirectory of CLONE_BASE_DIR,
namespaced by owner_id and repository ID to avoid collisions.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class CloneError(Exception):
    """Raised when git clone fails."""


class GitNotAvailable(Exception):
    """Raised when git is not installed or not on PATH."""


def _require_git() -> str:
    """Return the path to the git executable or raise GitNotAvailable."""
    git = shutil.which("git")
    if git is None:
        raise GitNotAvailable(
            "git is not installed or not available on PATH. "
            "Install git to enable repository cloning."
        )
    return git


def clone_repository(
    clone_url: str,
    owner_id: str,
    repository_id: str,
    branch: str,
) -> Path:
    """
    Clone a public GitHub repository to local storage.

    The clone is placed at:
        <CLONE_BASE_DIR>/<owner_id>/<repository_id>/

    If a clone already exists at that path it is removed first so the
    caller always gets a fresh, consistent clone.

    Parameters
    ----------
    clone_url:
        HTTPS URL of the public GitHub repository (no credentials).
    owner_id:
        Application user UUID who owns this repository record.
    repository_id:
        Database UUID of the Repository row.
    branch:
        The branch to clone (passed to --branch).

    Returns
    -------
    Path
        Absolute path to the cloned repository on disk.

    Raises
    ------
    GitNotAvailable
        git executable is missing.
    CloneError
        git clone exited with a non-zero status.
    """
    git = _require_git()

    dest: Path = Path(settings.clone_base_dir) / owner_id / repository_id

    # Remove stale clone so we always start clean.
    if dest.exists():
        logger.info("Removing existing clone at %s", dest)
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning %s (branch=%s) → %s", clone_url, branch, dest)

    cmd = [
        git,
        "clone",
        "--branch", branch,
        "--single-branch",
        "--depth", "1",
        clone_url,
        str(dest),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute hard limit per clone
        )
    except subprocess.TimeoutExpired as exc:
        raise CloneError(
            f"git clone timed out for repository {repository_id}."
        ) from exc
    except OSError as exc:
        raise CloneError(
            f"Failed to launch git for repository {repository_id}: {exc}"
        ) from exc

    if result.returncode != 0:
        logger.error(
            "git clone failed (exit %d):\nstdout: %s\nstderr: %s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        raise CloneError(
            f"git clone failed for {clone_url!r} "
            f"(exit code {result.returncode}): {result.stderr.strip()}"
        )

    logger.info("Clone successful: %s", dest)
    return dest
