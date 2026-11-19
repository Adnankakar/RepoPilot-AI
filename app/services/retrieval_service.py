"""
retrieval_service.py

Core Retrieval Service for RepoPilot AI.

Purpose:
Find the code and documentation chunks that are most relevant to a user's question,
subject to strict repository authorization boundaries and an insufficient-evidence
relevance threshold.

Tasks & Responsibilities:
1. Vector Similarity Search:
   Leverages dense vector embeddings and pgvector cosine distance queries (with
   in-memory fallback) to perform nearest-neighbor semantic search over indexed CodeChunk rows.
2. Relevant Chunks Retrieval:
   Encodes user queries with the configured EmbeddingProvider, runs similarity search,
   and ranks chunks by semantic similarity score (1 - cosine_distance).
3. Authorization Scoping:
   Strictly filters every query by the repositories the authenticated user is authorized
   to access. Attempts to query unauthorized repositories raise UnauthorizedRepositoryAccessError.
4. Insufficient-Evidence Threshold:
   Applies an empirical threshold (default 0.50) to filter out spurious nearest neighbors.
   If no candidate chunk meets the threshold, the system flags insufficient evidence and
   returns an empty chunk set, preventing LLM hallucination on irrelevant code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.user import User, UserRole
from app.services.embedding_provider import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)
from app.services.embedding_service import search_similar_chunks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RetrievalError(Exception):
    """Base exception for retrieval service failures."""


class UnauthorizedRepositoryAccessError(RetrievalError):
    """Raised when a user attempts to retrieve code from repositories they do not own or access."""


class EmptyQueryError(RetrievalError):
    """Raised when an empty or whitespace-only search query is supplied."""


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    """A single retrieved code chunk with similarity metrics and source metadata."""

    id: str
    repository_id: str
    file_path: str
    chunk_index: int
    start_line: int
    end_line: int
    content: str
    similarity: float
    distance: float
    commit_sha: str | None = None
    chunk: CodeChunk | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repository_id": self.repository_id,
            "file_path": self.file_path,
            "chunk_index": self.chunk_index,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "similarity": round(self.similarity, 4),
            "distance": round(self.distance, 4),
            "commit_sha": self.commit_sha,
        }


@dataclass
class RetrievalResult:
    """The complete result of a question retrieval query."""

    question: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    all_candidates: list[RetrievedChunk] = field(default_factory=list)
    has_sufficient_evidence: bool = False
    threshold: float = 0.50
    best_score: float | None = None
    searched_repositories: list[str] = field(default_factory=list)
    insufficient_evidence_reason: str | None = None
    message: str = "Retrieval completed."

    @property
    def top_chunk(self) -> RetrievedChunk | None:
        """Return the highest ranked chunk if available, otherwise None."""
        return self.chunks[0] if self.chunks else None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "has_sufficient_evidence": self.has_sufficient_evidence,
            "threshold": self.threshold,
            "best_score": round(self.best_score, 4) if self.best_score is not None else None,
            "chunks": [c.to_dict() for c in self.chunks],
            "searched_repositories": self.searched_repositories,
            "insufficient_evidence_reason": self.insufficient_evidence_reason,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Authorization Scoping (Task 3)
# ---------------------------------------------------------------------------


def extract_user_id(user: User | str | UUID | dict) -> str:
    """Extract string user ID from various user representations."""
    if isinstance(user, dict):
        uid = user.get("id") or user.get("sub")
        if uid is not None:
            return str(uid)
    elif hasattr(user, "id"):
        return str(user.id)
    elif isinstance(user, (str, UUID)):
        return str(user)
    raise ValueError(f"Unable to extract user ID from: {user!r}")


def is_user_admin(user: User | str | UUID | dict) -> bool:
    """Determine whether the given user has administrator privileges."""
    if isinstance(user, User):
        return user.role == UserRole.ADMINISTRATOR
    if isinstance(user, dict):
        role = user.get("role")
        return role in (UserRole.ADMINISTRATOR, "administrator", "admin")
    return False


def resolve_authorized_repositories(
    db: Session,
    user: User | str | UUID | dict,
    requested_repository_ids: Sequence[str] | str | None = None,
) -> list[str]:
    """
    Determine the set of repository IDs that the user is permitted to search over.

    Rules:
    1. Standard users may only access repositories where `Repository.owner_id == user_id`.
    2. Administrators may access any existing repository.
    3. If `requested_repository_ids` is provided, all requested repositories are validated
       against the user's permissions. If any requested repository is unauthorized,
       `UnauthorizedRepositoryAccessError` is raised.
    4. If `requested_repository_ids` is omitted or empty, all repositories owned by the user
       (or all existing repositories for admins) are returned.

    Returns:
        A list of validated repository ID strings.
    """
    user_id = extract_user_id(user)
    admin = is_user_admin(user)

    # Normalize requested repository IDs
    requested_list: list[str] = []
    if requested_repository_ids is not None:
        if isinstance(requested_repository_ids, str):
            requested_list = [requested_repository_ids.strip()]
        else:
            requested_list = [r.strip() for r in requested_repository_ids if r and r.strip()]

    if admin:
        if requested_list:
            # For admin, verify requested repositories exist
            stmt = select(Repository.id).where(Repository.id.in_(requested_list))
            found_ids = set(db.scalars(stmt).all())
            missing = set(requested_list) - found_ids
            if missing:
                raise UnauthorizedRepositoryAccessError(
                    f"Repository not found or inaccessible: {', '.join(sorted(missing))}"
                )
            return list(found_ids)
        else:
            # All repositories
            return list(db.scalars(select(Repository.id)).all())

    # For standard users, verify against owner_id
    if requested_list:
        stmt = select(Repository.id).where(
            Repository.id.in_(requested_list),
            Repository.owner_id == user_id,
        )
        authorized_ids = set(db.scalars(stmt).all())
        unauthorized = set(requested_list) - authorized_ids
        if unauthorized:
            raise UnauthorizedRepositoryAccessError(
                f"User is not authorized to access repository: {', '.join(sorted(unauthorized))}"
            )
        return list(authorized_ids)
    else:
        # All repositories owned by this user
        stmt = select(Repository.id).where(Repository.owner_id == user_id)
        return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Vector Similarity Search (Task 1)
# ---------------------------------------------------------------------------


def execute_vector_similarity_search(
    db: Session,
    query_vector: list[float],
    repository_ids: Sequence[str],
    limit: int = 10,
) -> list[RetrievedChunk]:
    """
    Execute vector similarity search for candidate chunks restricted to authorized repository IDs.

    Calculates cosine similarity as:
        cosine_similarity = 1.0 - cosine_distance

    Returns:
        List of RetrievedChunk instances ordered by similarity descending (highest score first).
    """
    if not repository_ids:
        return []

    # Query CodeChunk rows using pgvector cosine distance
    raw_results = search_similar_chunks(
        db=db,
        query_vector=query_vector,
        repository_ids=repository_ids,
        limit=limit,
    )

    retrieved: list[RetrievedChunk] = []
    for chunk, distance in raw_results:
        # Clamp distance and calculate similarity
        clamped_dist = max(0.0, float(distance))
        sim = max(-1.0, min(1.0, 1.0 - clamped_dist))
        retrieved.append(
            RetrievedChunk(
                id=chunk.id,
                repository_id=chunk.repository_id,
                file_path=chunk.file_path,
                chunk_index=chunk.chunk_index,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                similarity=sim,
                distance=clamped_dist,
                commit_sha=chunk.commit_sha,
                chunk=chunk,
            )
        )

    # Sort primarily by similarity descending, secondarily by distance ascending
    retrieved.sort(key=lambda c: (-c.similarity, c.distance))
    return retrieved


# ---------------------------------------------------------------------------
# Retrieval Service (Task 2 & Task 4)
# ---------------------------------------------------------------------------


def retrieve_relevant_chunks(
    db: Session,
    question: str,
    user: User | str | UUID | dict,
    repository_id: str | None = None,
    repository_ids: Sequence[str] | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    provider: EmbeddingProvider | None = None,
) -> RetrievalResult:
    """
    Retrieve code chunks relevant to a question with repository access control
    and an insufficient-evidence similarity threshold.

    Parameters:
        db: Active SQLAlchemy database session.
        question: User query or natural language question.
        user: Authenticated user object or ID used for authorization filtering.
        repository_id: Optional single repository ID to search.
        repository_ids: Optional collection of repository IDs to search.
        top_k: Maximum number of relevant chunks to return (default: settings.retrieval_top_k).
        similarity_threshold: Minimum cosine similarity score required for relevance
            (default: settings.retrieval_similarity_threshold, 0.50).
        provider: EmbeddingProvider instance (defaults to global cached provider).

    Returns:
        RetrievalResult containing filtered chunks, evidence evaluation, and metadata.
    """
    # 1. Resolve configuration defaults
    effective_top_k = top_k if top_k is not None else settings.retrieval_top_k
    if effective_top_k <= 0:
        raise ValueError("top_k must be a positive integer.")

    effective_threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else settings.retrieval_similarity_threshold
    )
    if not (0.0 <= effective_threshold <= 1.0):
        raise ValueError("similarity_threshold must be between 0.0 and 1.0.")

    effective_provider = provider or get_embedding_provider()

    # 2. Validate question input
    clean_question = (question or "").strip()
    if not clean_question:
        return RetrievalResult(
            question=question or "",
            chunks=[],
            all_candidates=[],
            has_sufficient_evidence=False,
            threshold=effective_threshold,
            best_score=None,
            searched_repositories=[],
            insufficient_evidence_reason="Empty or whitespace-only search question provided.",
            message="No question provided.",
        )

    # 3. Resolve and authorize target repositories (Task 3)
    target_repos_filter: list[str] | None = None
    if repository_ids is not None:
        target_repos_filter = list(repository_ids)
    if repository_id is not None:
        if target_repos_filter is None:
            target_repos_filter = [repository_id]
        elif repository_id not in target_repos_filter:
            target_repos_filter.append(repository_id)

    authorized_repo_ids = resolve_authorized_repositories(
        db=db,
        user=user,
        requested_repository_ids=target_repos_filter,
    )

    if not authorized_repo_ids:
        logger.info(
            "User %s has no accessible repositories for question: %s",
            extract_user_id(user),
            clean_question,
        )
        return RetrievalResult(
            question=clean_question,
            chunks=[],
            all_candidates=[],
            has_sufficient_evidence=False,
            threshold=effective_threshold,
            best_score=None,
            searched_repositories=[],
            insufficient_evidence_reason="User has no accessible repositories indexed.",
            message="No accessible repositories found.",
        )

    # 4. Generate query vector embedding (Task 1 / 2)
    try:
        query_vector = effective_provider.embed(clean_question)
    except EmbeddingError as exc:
        logger.error("Failed to generate embedding for query '%s': %s", clean_question, exc)
        raise RetrievalError(f"Embedding generation failed: {exc}") from exc

    if len(query_vector) != effective_provider.dimension:
        raise RetrievalError(
            f"Query embedding dimension mismatch: got {len(query_vector)}, expected {effective_provider.dimension}"
        )

    # 5. Execute vector similarity search
    candidates = execute_vector_similarity_search(
        db=db,
        query_vector=query_vector,
        repository_ids=authorized_repo_ids,
        limit=effective_top_k,
    )

    if not candidates:
        logger.info(
            "No chunks found in repositories %s for question '%s'",
            authorized_repo_ids,
            clean_question,
        )
        return RetrievalResult(
            question=clean_question,
            chunks=[],
            all_candidates=[],
            has_sufficient_evidence=False,
            threshold=effective_threshold,
            best_score=None,
            searched_repositories=authorized_repo_ids,
            insufficient_evidence_reason="No indexed code chunks found in authorized repositories.",
            message="No indexed chunks found.",
        )

    # 6. Evaluate insufficient-evidence threshold (Task 4)
    best_score = max(c.similarity for c in candidates)
    passing_chunks = [c for c in candidates if c.similarity >= effective_threshold]

    if not passing_chunks:
        reason = (
            f"No chunks met the similarity threshold of {effective_threshold:.2f} "
            f"(highest similarity was {best_score:.2f})."
        )
        logger.info(
            "Insufficient evidence for question '%s': %s",
            clean_question,
            reason,
        )
        return RetrievalResult(
            question=clean_question,
            chunks=[],
            all_candidates=candidates,
            has_sufficient_evidence=False,
            threshold=effective_threshold,
            best_score=best_score,
            searched_repositories=authorized_repo_ids,
            insufficient_evidence_reason=reason,
            message="Insufficient evidence found for the question.",
        )

    # Evidence is sufficient
    return RetrievalResult(
        question=clean_question,
        chunks=passing_chunks,
        all_candidates=candidates,
        has_sufficient_evidence=True,
        threshold=effective_threshold,
        best_score=best_score,
        searched_repositories=authorized_repo_ids,
        insufficient_evidence_reason=None,
        message=f"Found {len(passing_chunks)} relevant chunk(s).",
    )


def batch_retrieve_relevant_chunks(
    db: Session,
    questions: Sequence[str],
    user: User | str | UUID | dict,
    repository_id: str | None = None,
    repository_ids: Sequence[str] | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[RetrievalResult]:
    """
    Retrieve relevant chunks for multiple questions efficiently using batch vectorization.

    Parameters:
        db: Active SQLAlchemy database session.
        questions: Collection of questions to search.
        user: Authenticated user object or ID.
        repository_id: Optional single repository ID filter.
        repository_ids: Optional collection of repository IDs filter.
        top_k: Max chunks per question.
        similarity_threshold: Minimum similarity threshold.
        provider: EmbeddingProvider instance.

    Returns:
        List of RetrievalResult objects corresponding to each input question.
    """
    effective_top_k = top_k if top_k is not None else settings.retrieval_top_k
    effective_threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else settings.retrieval_similarity_threshold
    )
    effective_provider = provider or get_embedding_provider()

    # Pre-resolve and validate repository authorizations once for the batch
    target_repos_filter: list[str] | None = None
    if repository_ids is not None:
        target_repos_filter = list(repository_ids)
    if repository_id is not None:
        if target_repos_filter is None:
            target_repos_filter = [repository_id]
        elif repository_id not in target_repos_filter:
            target_repos_filter.append(repository_id)

    authorized_repo_ids = resolve_authorized_repositories(
        db=db,
        user=user,
        requested_repository_ids=target_repos_filter,
    )

    if not authorized_repo_ids:
        return [
            RetrievalResult(
                question=q,
                chunks=[],
                all_candidates=[],
                has_sufficient_evidence=False,
                threshold=effective_threshold,
                best_score=None,
                searched_repositories=[],
                insufficient_evidence_reason="User has no accessible repositories indexed.",
                message="No accessible repositories found.",
            )
            for q in questions
        ]

    # Clean and filter non-empty questions
    cleaned_questions = [q.strip() for q in questions]
    non_empty_indices = [i for i, q in enumerate(cleaned_questions) if q]

    if not non_empty_indices:
        return [
            RetrievalResult(
                question=q,
                chunks=[],
                all_candidates=[],
                has_sufficient_evidence=False,
                threshold=effective_threshold,
                best_score=None,
                searched_repositories=[],
                insufficient_evidence_reason="Empty or whitespace-only search question provided.",
                message="No question provided.",
            )
            for q in questions
        ]

    # Batch embed valid questions
    queries_to_embed = [cleaned_questions[i] for i in non_empty_indices]
    try:
        vectors = effective_provider.embed_batch(queries_to_embed)
    except EmbeddingError as exc:
        logger.error("Batch embedding generation failed: %s", exc)
        raise RetrievalError(f"Batch embedding generation failed: {exc}") from exc

    results: list[RetrievalResult] = []
    vector_idx = 0
    for i, orig_q in enumerate(questions):
        clean_q = cleaned_questions[i]
        if not clean_q:
            results.append(
                RetrievalResult(
                    question=orig_q,
                    chunks=[],
                    all_candidates=[],
                    has_sufficient_evidence=False,
                    threshold=effective_threshold,
                    best_score=None,
                    searched_repositories=[],
                    insufficient_evidence_reason="Empty or whitespace-only search question provided.",
                    message="No question provided.",
                )
            )
            continue

        q_vec = vectors[vector_idx]
        vector_idx += 1

        candidates = execute_vector_similarity_search(
            db=db,
            query_vector=q_vec,
            repository_ids=authorized_repo_ids,
            limit=effective_top_k,
        )

        if not candidates:
            results.append(
                RetrievalResult(
                    question=clean_q,
                    chunks=[],
                    all_candidates=[],
                    has_sufficient_evidence=False,
                    threshold=effective_threshold,
                    best_score=None,
                    searched_repositories=authorized_repo_ids,
                    insufficient_evidence_reason="No indexed code chunks found in authorized repositories.",
                    message="No indexed chunks found.",
                )
            )
            continue

        best_score = max(c.similarity for c in candidates)
        passing = [c for c in candidates if c.similarity >= effective_threshold]

        if not passing:
            results.append(
                RetrievalResult(
                    question=clean_q,
                    chunks=[],
                    all_candidates=candidates,
                    has_sufficient_evidence=False,
                    threshold=effective_threshold,
                    best_score=best_score,
                    searched_repositories=authorized_repo_ids,
                    insufficient_evidence_reason=(
                        f"No chunks met the similarity threshold of {effective_threshold:.2f} "
                        f"(highest similarity was {best_score:.2f})."
                    ),
                    message="Insufficient evidence found for the question.",
                )
            )
        else:
            results.append(
                RetrievalResult(
                    question=clean_q,
                    chunks=passing,
                    all_candidates=candidates,
                    has_sufficient_evidence=True,
                    threshold=effective_threshold,
                    best_score=best_score,
                    searched_repositories=authorized_repo_ids,
                    insufficient_evidence_reason=None,
                    message=f"Found {len(passing)} relevant chunk(s).",
                )
            )

    return results
