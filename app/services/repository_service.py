import logging
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.repository_security import (
    RepositoryURLValidationError,
    parse_github_repo_url,
)
from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.services.clone_service import CloneError, GitNotAvailable, clone_repository
from app.services.file_discovery_service import discover_files
from app.services.file_persistence_service import persist_discovered_files
from app.services.github_provider import (
    GitHubProvider,
    GitHubRepositoryEmpty,
    GitHubRepositoryNotFound,
    GitHubProviderUnavailable,
)

logger = logging.getLogger(__name__)


class RepositoryAlreadyRegistered(Exception):
    pass


class RepositoryRegistrationError(Exception):
    pass


def _cleanup_clone(owner_id: str, repository_id: str) -> None:
    """Remove the clone directory for *repository_id* if it exists.

    Called on any ingestion failure that occurs after a successful clone so
    the disk is left clean and consistent with the failure status in the DB.
    Errors during removal are logged but not re-raised.
    """
    clone_dir: Path = Path(settings.clone_base_dir) / owner_id / repository_id
    if clone_dir.exists():
        try:
            shutil.rmtree(clone_dir)
            logger.info("Removed clone directory after failure: %s", clone_dir)
        except OSError as exc:
            logger.warning("Could not remove clone directory %s: %s", clone_dir, exc)


def register_repository(
    db: Session,
    owner_id: str,
    repo_url: str,
) -> tuple[Repository, IndexingJob]:
    try:
        owner, name, canonical_url = parse_github_repo_url(repo_url)
    except RepositoryURLValidationError:
        raise

    provider = GitHubProvider()

    try:
        info = provider.get_repository(owner, name)
    except (
        GitHubRepositoryNotFound,
        GitHubRepositoryEmpty,
        GitHubProviderUnavailable,
    ):
        raise

    existing = db.scalar(
        select(Repository).where(
            Repository.owner_id == str(owner_id),
            Repository.provider == "github",
            Repository.external_id == info.external_id,
        )
    )

    if existing:
        raise RepositoryAlreadyRegistered(
            "You have already registered this repository."
        )

    repository = Repository(
        owner_id=str(owner_id),
        provider="github",
        external_id=info.external_id,
        url=info.url or canonical_url,
        default_branch=info.default_branch,
        indexed_commit=None,
        status="pending",
    )

    try:
        db.add(repository)
        db.flush()

        job = IndexingJob(
            repository_id=repository.id,
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(repository)
        db.refresh(job)

    except IntegrityError as exc:
        db.rollback()
        raise RepositoryAlreadyRegistered(
            "You have already registered this repository."
        ) from exc
    except Exception:
        db.rollback()
        raise

    # Clone the repository after the DB records are committed.
    try:
        clone_path = clone_repository(
            clone_url=repository.url,
            owner_id=str(owner_id),
            repository_id=repository.id,
            branch=repository.default_branch,
        )

        # Discover files in the freshly cloned repository.
        discovery = discover_files(clone_path)

        # Persist metadata — status is only set AFTER this succeeds so
        # that a DB failure here does not leave "cloned" committed.
        try:
            file_count = persist_discovered_files(db, repository.id, discovery)
        except Exception as exc:
            # Persistence failed — roll back the file inserts, clean up the
            # clone directory, and record the failure in the status columns.
            db.rollback()
            _cleanup_clone(str(owner_id), repository.id)
            logger.error(
                "File persistence failed for repository %s: %s",
                repository.id,
                exc,
            )
            repository.status = "ingestion_failed"
            job.status = "ingestion_failed"
            raise

        if discovery.stop_reason:
            repository.status = "partial"
            job.status = "partial"
            logger.warning(
                "Discovery incomplete for repository %s: %s",
                repository.id,
                discovery.stop_reason,
            )
        else:
            repository.status = "cloned"
            job.status = "cloned"

        logger.info(
            "Saved %d file records for repository %s",
            file_count,
            repository.id,
        )

    except (CloneError, GitNotAvailable) as exc:
        logger.warning(
            "Clone failed for repository %s: %s", repository.id, exc
        )
        repository.status = "clone_failed"
        job.status = "clone_failed"
    finally:
        db.add(repository)
        db.add(job)
        db.commit()
        db.refresh(repository)
        db.refresh(job)

    return repository, job