"""
retrieval.py

FastAPI router for Retrieval Service endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.retrieval import (
    BatchRetrievalQueryRequest,
    BatchRetrievalResponse,
    RetrievalQueryRequest,
    RetrievalResponse,
    RetrievedChunkResponse,
)
from app.services.retrieval_service import (
    RetrievalError,
    UnauthorizedRepositoryAccessError,
    batch_retrieve_relevant_chunks,
    retrieve_relevant_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieval", tags=["Retrieval"])


@router.post(
    "/query",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve relevant code chunks for a single question",
)
def query_retrieval(
    payload: RetrievalQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RetrievalResponse:
    """
    Search indexed code chunks using vector similarity and return relevant results.

    - Vector Similarity: Compares query embedding against chunk vectors.
    - Repository Authorization: Confirms the user owns or is authorized to query requested repositories.
    - Insufficient-Evidence Filter: Applies similarity threshold (default 0.50); if no chunks meet
      the threshold, has_sufficient_evidence is set to False with an explanatory reason.
    """
    try:
        result = retrieve_relevant_chunks(
            db=db,
            question=payload.question,
            user=current_user,
            repository_id=payload.repository_id,
            repository_ids=payload.repository_ids,
            top_k=payload.top_k,
            similarity_threshold=payload.similarity_threshold,
        )
    except UnauthorizedRepositoryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return RetrievalResponse(
        question=result.question,
        has_sufficient_evidence=result.has_sufficient_evidence,
        threshold=result.threshold,
        best_score=result.best_score,
        chunks=[
            RetrievedChunkResponse(
                id=c.id,
                repository_id=c.repository_id,
                file_path=c.file_path,
                chunk_index=c.chunk_index,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                similarity=round(c.similarity, 4),
                distance=round(c.distance, 4),
                commit_sha=c.commit_sha,
            )
            for c in result.chunks
        ],
        searched_repositories=result.searched_repositories,
        insufficient_evidence_reason=result.insufficient_evidence_reason,
        message=result.message,
    )


@router.post(
    "/batch",
    response_model=BatchRetrievalResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve relevant code chunks for multiple questions in batch",
)
def batch_query_retrieval(
    payload: BatchRetrievalQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchRetrievalResponse:
    """
    Process multiple questions in batch, vectorizing queries together and retrieving
    relevant chunks with repository authorization and evidence threshold filtering.
    """
    try:
        results = batch_retrieve_relevant_chunks(
            db=db,
            questions=payload.questions,
            user=current_user,
            repository_id=payload.repository_id,
            repository_ids=payload.repository_ids,
            top_k=payload.top_k,
            similarity_threshold=payload.similarity_threshold,
        )
    except UnauthorizedRepositoryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    serialized_results: list[RetrievalResponse] = []
    questions_with_evidence = 0

    for res in results:
        if res.has_sufficient_evidence:
            questions_with_evidence += 1

        serialized_results.append(
            RetrievalResponse(
                question=res.question,
                has_sufficient_evidence=res.has_sufficient_evidence,
                threshold=res.threshold,
                best_score=res.best_score,
                chunks=[
                    RetrievedChunkResponse(
                        id=c.id,
                        repository_id=c.repository_id,
                        file_path=c.file_path,
                        chunk_index=c.chunk_index,
                        start_line=c.start_line,
                        end_line=c.end_line,
                        content=c.content,
                        similarity=round(c.similarity, 4),
                        distance=round(c.distance, 4),
                        commit_sha=c.commit_sha,
                    )
                    for c in res.chunks
                ],
                searched_repositories=res.searched_repositories,
                insufficient_evidence_reason=res.insufficient_evidence_reason,
                message=res.message,
            )
        )

    return BatchRetrievalResponse(
        results=serialized_results,
        total_questions=len(payload.questions),
        questions_with_evidence=questions_with_evidence,
    )
