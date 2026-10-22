from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.repository_security import (
    RepositoryURLValidationError,
    parse_github_repo_url,
)
from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.services.github_provider import (
    GitHubProvider,
    GitHubRepositoryEmpty,
    GitHubRepositoryNotFound,
    GitHubProviderUnavailable,
)


class RepositoryAlreadyRegistered(Exception):
    pass


class RepositoryRegistrationError(Exception):
    pass


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

        return repository, job

    except IntegrityError as exc:
        db.rollback()
        raise RepositoryAlreadyRegistered(
            "You have already registered this repository."
        ) from exc
    except Exception:
        db.rollback()
        raise