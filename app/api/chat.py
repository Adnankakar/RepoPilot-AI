"""
chat.py

FastAPI router for the LLM-powered Q&A endpoint.
Retrieves semantically relevant code chunks via vector search, then sends
them as grounded context to OpenRouter and returns a natural-language answer.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatAskRequest, ChatAskResponse
from app.services.embedding_provider import get_embedding_provider
from app.services.retrieval_service import (
    RetrievalError,
    UnauthorizedRepositoryAccessError,
    retrieve_relevant_chunks,
)
from app.core.rag_orchestration import OpenRouterProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


def _build_prompt(question: str, chunks) -> str:
    """Build a focused prompt with retrieved code evidence."""
    if not chunks:
        return ""

    evidence_lines = []
    for c in chunks:
        evidence_lines.append(
            f"### File: {c.file_path} (lines {c.start_line}–{c.end_line})\n"
            f"```\n{c.content.strip()}\n```"
        )
    evidence_block = "\n\n".join(evidence_lines)

    return (
        "You are a helpful code assistant. Use the following code excerpts "
        "to answer the user's question clearly and concisely. "
        "Reference the specific file and line numbers when relevant. "
        "Do NOT invent code that is not present in the excerpts.\n\n"
        f"## Retrieved Code Evidence\n\n{evidence_block}\n\n"
        f"## Question\n\n{question}\n\n"
        "## Answer"
    )


@router.post(
    "/ask",
    response_model=ChatAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about indexed code and get an LLM-generated answer",
)
def ask_question(
    payload: ChatAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatAskResponse:
    """
    Two-stage Q&A:
    1. Vector similarity search retrieves the most relevant code chunks.
    2. OpenRouter LLM generates a grounded natural-language answer.

    If no chunks meet the similarity threshold the endpoint returns
    has_sufficient_evidence=False with an explanation and no LLM call is made.

    Embedding dimension mismatch (e.g. repo indexed with one model and queried
    with another) is detected early and surfaces as a clear 409 error.
    """
    # ── Dimension guard: catch model mismatch before wasting a retrieval call ─
    provider = get_embedding_provider()
    stored_dim = settings.embedding_dimension
    if provider.dimension != stored_dim:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Embedding dimension mismatch: the active model '{settings.embedding_model}' "
                f"produces {provider.dimension}-dimensional vectors, but the database was indexed "
                f"with {stored_dim}-dimensional vectors. Re-index your repositories with the "
                f"current model before querying."
            ),
        )

    # ── Stage 1: Retrieval ────────────────────────────────────────────────────
    try:
        retrieval = retrieve_relevant_chunks(
            db=db,
            question=payload.question,
            user=current_user,
            repository_id=payload.repository_id,
            repository_ids=payload.repository_ids,
            top_k=payload.top_k,
            similarity_threshold=payload.similarity_threshold,
            provider=provider,
        )
    except UnauthorizedRepositoryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    if not retrieval.has_sufficient_evidence or not retrieval.chunks:
        return ChatAskResponse(
            question=payload.question,
            answer=None,
            has_sufficient_evidence=False,
            insufficient_evidence_reason=(
                retrieval.insufficient_evidence_reason
                or "No relevant code found above the similarity threshold."
            ),
            best_score=retrieval.best_score,
            threshold=retrieval.threshold,
            chunks_used=0,
            searched_repositories=retrieval.searched_repositories,
        )

    # ── Stage 2: LLM answer generation ───────────────────────────────────────
    prompt = _build_prompt(payload.question, retrieval.chunks)

    try:
        llm = OpenRouterProvider()
        answer = llm.call_llm(prompt)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider is unavailable: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected LLM error for question: %s", payload.question)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating the answer.",
        ) from exc

    return ChatAskResponse(
        question=payload.question,
        answer=answer,
        has_sufficient_evidence=True,
        insufficient_evidence_reason=None,
        best_score=retrieval.best_score,
        threshold=retrieval.threshold,
        chunks_used=len(retrieval.chunks),
        searched_repositories=retrieval.searched_repositories,
    )
