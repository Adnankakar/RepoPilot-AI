"""
test_retrieval_service.py

Unit and integration tests for the Retrieval Service:
1. Vector similarity search and score calculation.
2. Question retrieval of relevant code chunks.
3. User authorization filtering (enforcing repository isolation between users).
4. Insufficient-evidence threshold evaluation.
5. Batch retrieval across multiple questions.
"""

from __future__ import annotations

from typing import Sequence
from uuid import uuid4

import pytest

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.user import User, UserRole
from app.services.embedding_provider import EmbeddingProvider
from app.services.retrieval_service import (
    RetrievedChunk,
    RetrievalResult,
    UnauthorizedRepositoryAccessError,
    batch_retrieve_relevant_chunks,
    execute_vector_similarity_search,
    extract_user_id,
    is_user_admin,
    resolve_authorized_repositories,
    retrieve_relevant_chunks,
)


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for tests."""

    def __init__(self, dimension: int = 384, default_vector: list[float] | None = None) -> None:
        self._dim = dimension
        self.default_vector = default_vector or ([0.1] * dimension)
        self.query_vectors: dict[str, list[float]] = {}
        self.calls: list[str] = []

    @property
    def dimension(self) -> int:
        return self._dim

    def set_vector_for_text(self, text: str, vector: list[float]) -> None:
        self.query_vectors[text] = vector

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.query_vectors.get(text, self.default_vector)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _create_repo_with_chunks(
    db_session,
    owner_id: str,
    repo_url: str = "https://github.com/example/repo",
    chunk_data: list[tuple[str, list[float]]] | None = None,
) -> tuple[Repository, list[CodeChunk]]:
    """Helper to seed a repository and code chunks with specified embeddings."""
    repo = Repository(
        owner_id=owner_id,
        provider="github",
        external_id=str(uuid4()),
        url=repo_url,
        default_branch="main",
        status="completed",
    )
    db_session.add(repo)
    db_session.flush()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/service.py",
        size_bytes=500,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.flush()

    chunks: list[CodeChunk] = []
    data = chunk_data or [
        ("def auth_handler():\n    return 'auth'", [1.0] + [0.0] * 383),
        ("def db_connect():\n    return 'db'", [0.0, 1.0] + [0.0] * 382),
        ("def helper():\n    return 'help'", [0.5, 0.5] + [0.0] * 382),
    ]

    for idx, (content, embedding) in enumerate(data):
        chunk = CodeChunk(
            repository_id=repo.id,
            file_id=file_row.id,
            file_path=file_row.path,
            commit_sha="commit_sha_123",
            chunk_index=idx,
            start_line=idx * 10 + 1,
            end_line=idx * 10 + 10,
            content=content,
            embedding=embedding,
        )
        db_session.add(chunk)
        chunks.append(chunk)

    db_session.flush()
    return repo, chunks


# ---------------------------------------------------------------------------
# Task 1: Vector Similarity Search Tests
# ---------------------------------------------------------------------------


def test_vector_similarity_search_ranking(db_session):
    """Vector similarity search returns chunks ordered by similarity descending (distance ascending)."""
    owner_id = str(uuid4())
    repo, chunks = _create_repo_with_chunks(db_session, owner_id)

    # Query vector identical to chunk 0
    query_vec = [1.0] + [0.0] * 383

    results = execute_vector_similarity_search(
        db=db_session,
        query_vector=query_vec,
        repository_ids=[repo.id],
        limit=5,
    )

    assert len(results) == 3
    # Chunk 0 has distance 0.0 -> similarity 1.0
    assert results[0].id == chunks[0].id
    assert pytest.approx(results[0].similarity, abs=0.01) == 1.0
    assert pytest.approx(results[0].distance, abs=0.01) == 0.0

    # Ensure all results are sorted by similarity descending
    for i in range(len(results) - 1):
        assert results[i].similarity >= results[i + 1].similarity


def test_vector_similarity_search_empty_repository_ids(db_session):
    """Searching with no repository IDs immediately returns an empty list."""
    query_vec = [1.0] + [0.0] * 383
    results = execute_vector_similarity_search(
        db=db_session,
        query_vector=query_vec,
        repository_ids=[],
        limit=5,
    )
    assert results == []


# ---------------------------------------------------------------------------
# Task 3: Repository Authorization Filtering Tests
# ---------------------------------------------------------------------------


def test_resolve_authorized_repositories_single_owner(db_session):
    """User only accesses repositories that they own."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    repo_a1, _ = _create_repo_with_chunks(db_session, owner_id=user_a, repo_url="https://github.com/a/repo1")
    repo_a2, _ = _create_repo_with_chunks(db_session, owner_id=user_a, repo_url="https://github.com/a/repo2")
    repo_b, _ = _create_repo_with_chunks(db_session, owner_id=user_b, repo_url="https://github.com/b/repo1")

    # When no specific repos requested, returns all repos owned by user_a
    authorized = resolve_authorized_repositories(db_session, user_a)
    assert set(authorized) == {repo_a1.id, repo_a2.id}
    assert repo_b.id not in authorized


def test_resolve_authorized_repositories_unauthorized_access_raises_error(db_session):
    """Attempting to request a repository owned by another user raises UnauthorizedRepositoryAccessError."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    repo_a, _ = _create_repo_with_chunks(db_session, owner_id=user_a, repo_url="https://github.com/a/repo1")
    repo_b, _ = _create_repo_with_chunks(db_session, owner_id=user_b, repo_url="https://github.com/b/repo1")

    with pytest.raises(UnauthorizedRepositoryAccessError) as exc_info:
        resolve_authorized_repositories(
            db=db_session,
            user=user_a,
            requested_repository_ids=[repo_b.id],
        )

    assert repo_b.id in str(exc_info.value)


def test_resolve_authorized_repositories_mixed_authorized_and_unauthorized(db_session):
    """If any requested repo is unauthorized, access is denied for safety."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    repo_a, _ = _create_repo_with_chunks(db_session, owner_id=user_a, repo_url="https://github.com/a/repo1")
    repo_b, _ = _create_repo_with_chunks(db_session, owner_id=user_b, repo_url="https://github.com/b/repo1")

    with pytest.raises(UnauthorizedRepositoryAccessError):
        resolve_authorized_repositories(
            db=db_session,
            user=user_a,
            requested_repository_ids=[repo_a.id, repo_b.id],
        )


def test_resolve_authorized_repositories_administrator(db_session):
    """Admin users are authorized across all repositories."""
    admin_user = User(
        email="admin@example.com",
        password_hash="fakehash",
        role=UserRole.ADMINISTRATOR,
    )
    dev_user_id = str(uuid4())
    repo_dev, _ = _create_repo_with_chunks(db_session, owner_id=dev_user_id, repo_url="https://github.com/dev/repo1")

    authorized = resolve_authorized_repositories(
        db=db_session,
        user=admin_user,
        requested_repository_ids=[repo_dev.id],
    )
    assert repo_dev.id in authorized


def test_user_without_repositories_returns_empty_list(db_session):
    """A user with 0 registered repositories returns an empty list without error."""
    new_user_id = str(uuid4())
    authorized = resolve_authorized_repositories(db_session, new_user_id)
    assert authorized == []


# ---------------------------------------------------------------------------
# Task 2 & Task 4: Retrieval Service and Insufficient Evidence Threshold Tests
# ---------------------------------------------------------------------------


def test_retrieve_relevant_chunks_sufficient_evidence(db_session):
    """Query matching a chunk above threshold returns sufficient evidence and ranked chunks."""
    owner_id = str(uuid4())
    repo, chunks = _create_repo_with_chunks(db_session, owner_id=owner_id)

    provider = MockEmbeddingProvider(dimension=384)
    # Set query vector to match chunk 0 perfectly
    provider.set_vector_for_text("How does authentication work?", [1.0] + [0.0] * 383)

    result = retrieve_relevant_chunks(
        db=db_session,
        question="How does authentication work?",
        user=owner_id,
        repository_id=repo.id,
        similarity_threshold=0.50,
        provider=provider,
    )

    assert result.has_sufficient_evidence is True
    assert len(result.chunks) >= 1
    assert result.chunks[0].id == chunks[0].id
    assert pytest.approx(result.chunks[0].similarity, abs=0.01) == 1.0
    assert result.insufficient_evidence_reason is None
    assert result.threshold == 0.50
    assert result.best_score is not None and result.best_score >= 0.50


def test_retrieve_relevant_chunks_insufficient_evidence_below_threshold(db_session):
    """When all candidate chunks have similarity below the threshold, insufficient evidence is flagged."""
    owner_id = str(uuid4())
    # Chunks are along axes 0, 1, 2
    repo, chunks = _create_repo_with_chunks(db_session, owner_id=owner_id)

    provider = MockEmbeddingProvider(dimension=384)
    # Query vector orthogonal to all chunks (e.g. axis 50)
    orthogonal_vec = [0.0] * 50 + [1.0] + [0.0] * 333
    provider.set_vector_for_text("Recipe for chocolate cake", orthogonal_vec)

    result = retrieve_relevant_chunks(
        db=db_session,
        question="Recipe for chocolate cake",
        user=owner_id,
        repository_id=repo.id,
        similarity_threshold=0.50,
        provider=provider,
    )

    assert result.has_sufficient_evidence is False
    assert len(result.chunks) == 0  # Filtered out!
    assert len(result.all_candidates) > 0  # Raw candidates still recorded for inspection
    assert result.insufficient_evidence_reason is not None
    assert "No chunks met the similarity threshold" in result.insufficient_evidence_reason


def test_retrieve_relevant_chunks_custom_threshold_override(db_session):
    """Custom similarity threshold parameter overrides system default."""
    owner_id = str(uuid4())
    # Chunk with similarity approx 0.707 to query [1.0, 0.0, ...]
    custom_chunk = ("def test(): pass", [0.7071, 0.7071] + [0.0] * 382)
    repo, chunks = _create_repo_with_chunks(
        db_session,
        owner_id=owner_id,
        chunk_data=[custom_chunk],
    )

    provider = MockEmbeddingProvider(dimension=384)
    provider.set_vector_for_text("query", [1.0] + [0.0] * 383)

    # With threshold 0.80, this 0.707 chunk should fail
    strict_res = retrieve_relevant_chunks(
        db=db_session,
        question="query",
        user=owner_id,
        repository_id=repo.id,
        similarity_threshold=0.80,
        provider=provider,
    )
    assert strict_res.has_sufficient_evidence is False
    assert len(strict_res.chunks) == 0

    # With threshold 0.60, this 0.707 chunk should pass
    lenient_res = retrieve_relevant_chunks(
        db=db_session,
        question="query",
        user=owner_id,
        repository_id=repo.id,
        similarity_threshold=0.60,
        provider=provider,
    )
    assert lenient_res.has_sufficient_evidence is True
    assert len(lenient_res.chunks) == 1


def test_retrieve_relevant_chunks_empty_question(db_session):
    """Empty or whitespace question returns safe empty result."""
    owner_id = str(uuid4())
    result = retrieve_relevant_chunks(
        db=db_session,
        question="   ",
        user=owner_id,
    )
    assert result.has_sufficient_evidence is False
    assert result.chunks == []
    assert "Empty or whitespace" in (result.insufficient_evidence_reason or "")


def test_retrieve_relevant_chunks_user_with_no_repos(db_session):
    """User with no repositories receives insufficient evidence result."""
    empty_user_id = str(uuid4())
    result = retrieve_relevant_chunks(
        db=db_session,
        question="Find user profile",
        user=empty_user_id,
    )
    assert result.has_sufficient_evidence is False
    assert result.chunks == []
    assert "User has no accessible repositories" in (result.insufficient_evidence_reason or "")


def test_retrieve_relevant_chunks_cross_repository_isolation(db_session):
    """User A cannot retrieve chunks belonging to User B."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    repo_a, _ = _create_repo_with_chunks(
        db_session,
        owner_id=user_a,
        repo_url="https://github.com/a/project",
        chunk_data=[("User A secret algorithm", [1.0] + [0.0] * 383)],
    )
    repo_b, _ = _create_repo_with_chunks(
        db_session,
        owner_id=user_b,
        repo_url="https://github.com/b/project",
        chunk_data=[("User B confidential token", [1.0] + [0.0] * 383)],
    )

    provider = MockEmbeddingProvider(dimension=384)
    provider.set_vector_for_text("confidential token", [1.0] + [0.0] * 383)

    # When User A searches across all their accessible repositories
    res_a = retrieve_relevant_chunks(
        db=db_session,
        question="confidential token",
        user=user_a,
        provider=provider,
    )

    # Only chunks from repo_a should ever be returned
    for chunk in res_a.chunks:
        assert chunk.repository_id == repo_a.id
        assert chunk.repository_id != repo_b.id

    # If User A explicitly tries to request repo_b, it must raise UnauthorizedRepositoryAccessError
    with pytest.raises(UnauthorizedRepositoryAccessError):
        retrieve_relevant_chunks(
            db=db_session,
            question="confidential token",
            user=user_a,
            repository_id=repo_b.id,
            provider=provider,
        )


# ---------------------------------------------------------------------------
# Batch Retrieval Tests
# ---------------------------------------------------------------------------


def test_batch_retrieve_relevant_chunks(db_session):
    """Batch retrieval processes multiple questions with batch embedding."""
    owner_id = str(uuid4())
    repo, chunks = _create_repo_with_chunks(db_session, owner_id=owner_id)

    provider = MockEmbeddingProvider(dimension=384)
    provider.set_vector_for_text("auth question", [1.0] + [0.0] * 383)
    provider.set_vector_for_text("db question", [0.0, 1.0] + [0.0] * 382)
    provider.set_vector_for_text("unrelated question", [0.0] * 100 + [1.0] + [0.0] * 283)

    questions = ["auth question", "db question", "unrelated question", "   "]

    results = batch_retrieve_relevant_chunks(
        db=db_session,
        questions=questions,
        user=owner_id,
        repository_id=repo.id,
        similarity_threshold=0.50,
        provider=provider,
    )

    assert len(results) == 4
    # Question 0 (auth): sufficient evidence
    assert results[0].has_sufficient_evidence is True
    assert results[0].chunks[0].id == chunks[0].id

    # Question 1 (db): sufficient evidence
    assert results[1].has_sufficient_evidence is True
    assert results[1].chunks[0].id == chunks[1].id

    # Question 2 (unrelated): insufficient evidence
    assert results[2].has_sufficient_evidence is False
    assert len(results[2].chunks) == 0

    # Question 3 (empty): handled cleanly
    assert results[3].has_sufficient_evidence is False
    assert len(results[3].chunks) == 0
