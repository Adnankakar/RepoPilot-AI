from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.repository_security import RepositoryURLValidationError
from app.db.session import get_db
from app.models.indexing_job import IndexingJob
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.schemas.indexing_job import (
    IndexingJobResponse,
    RepositoryStatusResponse,
    TriggerIndexingResponse,
)
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryRegistrationResponse,
    RepositoryResponse,
)
from app.schemas.repository_file import RepositoryFileResponse
from app.schemas.repository_file_skip import RepositoryFileSkipResponse
from app.services.github_provider import (
    GitHubProviderUnavailable,
    GitHubRepositoryEmpty,
    GitHubRepositoryNotFound,
)
from app.services.repository_service import (
    RepositoryAlreadyRegistered,
    register_repository,
)
from app.worker.indexing_worker import run_indexing_job

router = APIRouter(prefix="/repositories", tags=["Repositories"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(current_user) -> str:
    user_id = (
        current_user.get("id")
        if isinstance(current_user, dict)
        else getattr(current_user, "id", None)
    )
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user.",
        )
    return str(user_id)


def _get_user_repository(db: Session, repository_id: str, owner_id: str) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")
    if repo.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this repository.")
    return repo


def _pagination(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=1000),
    skip: int | None = Query(default=None, ge=0),
) -> tuple[int, int]:
    effective_limit = page_size if page_size is not None else limit
    if page is not None:
        effective_offset = (page - 1) * effective_limit
    elif skip is not None:
        effective_offset = skip
    else:
        effective_offset = offset
    return effective_limit, effective_offset


# ---------------------------------------------------------------------------
# Repository registration  (POST /repositories)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=RepositoryRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_repository(
    payload: RepositoryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = _get_user_id(current_user)

    try:
        repository, job = register_repository(
            db=db,
            owner_id=owner_id,
            repo_url=str(payload.url),
        )
    except RepositoryURLValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GitHubRepositoryEmpty as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GitHubProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Dispatch the ingestion pipeline as a background task.
    background_tasks.add_task(run_indexing_job, job.id)

    return {
        "repository": repository,
        "indexing_job_id": job.id,
        "message": "Repository registered. Indexing job queued.",
    }


# ---------------------------------------------------------------------------
# List repositories  (GET /repositories)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = _get_user_id(current_user)
    stmt = (
        select(Repository)
        .where(Repository.owner_id == owner_id)
        .order_by(Repository.created_at.desc())
    )
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Trigger indexing job  (POST /repositories/{id}/jobs)
# ---------------------------------------------------------------------------

@router.post(
    "/{repository_id}/jobs",
    response_model=TriggerIndexingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_indexing(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new indexing job for an existing repository and queue it for
    background execution. Returns HTTP 202 immediately.
    """
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    # Prevent queuing a new job while one is already running or queued.
    active = db.scalars(
        select(IndexingJob).where(
            IndexingJob.repository_id == repository_id,
            IndexingJob.status.in_(("queued", "running")),
        )
    ).first()
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An indexing job is already queued or running for this repository.",
        )

    job = IndexingJob(repository_id=repository_id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_indexing_job, job.id)

    return TriggerIndexingResponse(
        indexing_job_id=job.id,
        job_id=job.id,
    )


@router.post(
    "/{repository_id}/index",
    response_model=TriggerIndexingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
def trigger_indexing_alias(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return trigger_indexing(
        repository_id=repository_id,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


# ---------------------------------------------------------------------------
# Repository status polling  (GET /repositories/{id}/status)
# ---------------------------------------------------------------------------

@router.get(
    "/{repository_id}/status",
    response_model=RepositoryStatusResponse,
)
def get_repository_status(
    repository_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get repository status and latest indexing job status for frontend polling.
    """
    owner_id = _get_user_id(current_user)
    repo = _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    latest_job = db.scalars(
        select(IndexingJob)
        .where(IndexingJob.repository_id == repository_id)
        .order_by(IndexingJob.created_at.desc())
    ).first()

    return RepositoryStatusResponse(
        repository_id=repo.id,
        status=repo.status,
        latest_job=latest_job,
    )


# ---------------------------------------------------------------------------
# Job status  (GET /repositories/{id}/jobs/{job_id})
# ---------------------------------------------------------------------------

@router.get(
    "/{repository_id}/jobs/{job_id}",
    response_model=IndexingJobResponse,
)
def get_indexing_job(
    repository_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    job = db.get(IndexingJob, job_id)
    if job is None or job.repository_id != repository_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Indexing job not found.")

    return job


# ---------------------------------------------------------------------------
# Latest job for repository (GET /repositories/{id}/jobs/latest)
# ---------------------------------------------------------------------------

@router.get(
    "/{repository_id}/jobs/latest",
    response_model=IndexingJobResponse,
)
def get_latest_indexing_job(
    repository_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the latest indexing job for a repository.
    """
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    job = db.scalars(
        select(IndexingJob)
        .where(IndexingJob.repository_id == repository_id)
        .order_by(IndexingJob.created_at.desc())
    ).first()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No indexing jobs found for this repository.",
        )

    return job


# ---------------------------------------------------------------------------
# List all jobs for a repository  (GET /repositories/{id}/jobs)
# ---------------------------------------------------------------------------

@router.get(
    "/{repository_id}/jobs",
    response_model=list[IndexingJobResponse],
)
def list_indexing_jobs(
    repository_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    jobs = list(
        db.scalars(
            select(IndexingJob)
            .where(IndexingJob.repository_id == repository_id)
            .order_by(IndexingJob.created_at.desc())
        ).all()
    )
    return jobs


# ---------------------------------------------------------------------------
# Repository files  (GET /repositories/{id}/files)
# ---------------------------------------------------------------------------

@router.get("/{repository_id}/files", response_model=list[RepositoryFileResponse])
def get_repository_files(
    repository_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    pagination: tuple[int, int] = Depends(_pagination),
):
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)
    effective_limit, effective_offset = pagination

    stmt = (
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repository_id)
        .order_by(RepositoryFile.path.asc(), RepositoryFile.id.asc())
        .offset(effective_offset)
        .limit(effective_limit)
    )
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Repository skips  (GET /repositories/{id}/skips)
# ---------------------------------------------------------------------------

@router.get("/{repository_id}/skips", response_model=list[RepositoryFileSkipResponse])
def get_repository_skips(
    repository_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    pagination: tuple[int, int] = Depends(_pagination),
):
    owner_id = _get_user_id(current_user)
    _get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)
    effective_limit, effective_offset = pagination

    stmt = (
        select(RepositoryFileSkip)
        .where(RepositoryFileSkip.repository_id == repository_id)
        .order_by(RepositoryFileSkip.path.asc(), RepositoryFileSkip.id.asc())
        .offset(effective_offset)
        .limit(effective_limit)
    )
    return list(db.scalars(stmt).all())
