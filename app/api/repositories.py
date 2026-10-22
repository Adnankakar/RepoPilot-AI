from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.repository_security import RepositoryURLValidationError
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.repository import Repository
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryRegistrationResponse,
    RepositoryResponse,
)
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