from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.repository_security import RepositoryURLValidationError
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.repository_file_skip import RepositoryFileSkip
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryRegistrationResponse,
    RepositoryResponse,
)
from app.schemas.repository_file import RepositoryFileResponse
from app.schemas.repository_file_skip import RepositoryFileSkipResponse
from app.services.github_provider import (
    GitHubRepositoryEmpty,
    GitHubRepositoryNotFound,
    GitHubProviderUnavailable,
)
from app.services.repository_service import (
    RepositoryAlreadyRegistered,
    register_repository,
)


router = APIRouter(prefix="/repositories", tags=["Repositories"])


def get_user_id(current_user) -> str:
    if isinstance(current_user, dict):
        user_id = current_user.get("id")
    else:
        user_id = getattr(current_user, "id", None)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user.",
        )

    return str(user_id)


@router.post(
    "",
    response_model=RepositoryRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_repository(
    payload: RepositoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = get_user_id(current_user)

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

    return {
        "repository": repository,
        "indexing_job_id": job.id,
        "message": "Repository registered. Indexing job created.",
    }


@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = get_user_id(current_user)

    statement = (
        select(Repository)
        .where(Repository.owner_id == owner_id)
        .order_by(Repository.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_user_repository(
    db: Session,
    repository_id: str,
    owner_id: str,
) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )
    if repo.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this repository.",
        )
    return repo


@router.get("/{repository_id}/files", response_model=list[RepositoryFileResponse])
def get_repository_files(
    repository_id: str,
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    page: int | None = Query(default=None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(default=None, ge=1, le=1000, description="Number of items per page"),
    skip: int | None = Query(default=None, ge=0, description="Alternative to offset"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = get_user_id(current_user)
    get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    effective_limit = page_size if page_size is not None else limit
    if page is not None:
        effective_offset = (page - 1) * effective_limit
    elif skip is not None:
        effective_offset = skip
    else:
        effective_offset = offset

    statement = (
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repository_id)
        .order_by(RepositoryFile.path.asc(), RepositoryFile.id.asc())
        .offset(effective_offset)
        .limit(effective_limit)
    )
    return list(db.scalars(statement).all())


@router.get("/{repository_id}/skips", response_model=list[RepositoryFileSkipResponse])
def get_repository_skips(
    repository_id: str,
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    page: int | None = Query(default=None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(default=None, ge=1, le=1000, description="Number of items per page"),
    skip: int | None = Query(default=None, ge=0, description="Alternative to offset"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    owner_id = get_user_id(current_user)
    get_user_repository(db=db, repository_id=repository_id, owner_id=owner_id)

    effective_limit = page_size if page_size is not None else limit
    if page is not None:
        effective_offset = (page - 1) * effective_limit
    elif skip is not None:
        effective_offset = skip
    else:
        effective_offset = offset

    statement = (
        select(RepositoryFileSkip)
        .where(RepositoryFileSkip.repository_id == repository_id)
        .order_by(RepositoryFileSkip.path.asc(), RepositoryFileSkip.id.asc())
        .offset(effective_offset)
        .limit(effective_limit)
    )
    return list(db.scalars(statement).all())