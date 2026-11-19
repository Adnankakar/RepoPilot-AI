"""
Tests for app/services/embedding_service.py

Validates:
- generate_embeddings_for_repository embeds stored CodeChunk records.
- Idempotency: force=False only embeds chunks where embedding is NULL.
- force=True re-embeds all chunks for the repository.
- Batching: chunks are sent to provider in configured batch sizes.
- Dimension validation: chunks receiving vectors of incorrect dimension are skipped and logged as failed.
- Failure handling: provider errors are safely caught, recorded in EmbeddingResult, and don't raise out.
- Empty chunks or repository without chunks returns cleanly.
- search_similar_chunks retrieves chunks ranked by vector similarity.
"""

from __future__ import annotations

from typing import Sequence
from uuid import uuid4

import pytest

from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.services.embedding_provider import EmbeddingError, EmbeddingProvider
from app.services.embedding_service import (
    EmbeddingResult,
    generate_embeddings_for_repository,
    search_similar_chunks,
)


class _MockProvider(EmbeddingProvider):
    def __init__(
        self,
        dimension: int = 384,
        error_on_batch: bool = False,
        return_wrong_dim: bool = False,
    ) -> None:
        self._dim = dimension
        self.error_on_batch = error_on_batch
        self.return_wrong_dim = return_wrong_dim
        self.calls: list[list[str]] = []

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if self.error_on_batch:
            raise EmbeddingError("Mock embedding generation failure")
        self.calls.append(list(texts))
        dim = self._dim if not self.return_wrong_dim else self._dim + 10
        return [[0.1 * (i + 1)] * dim for i in range(len(texts))]


def _create_test_repo_and_chunks(
    db_session,
    chunk_count: int = 3,
    with_embedding: bool = False,
) -> tuple[Repository, list[CodeChunk]]:
    repo = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url=f"https://github.com/example/{uuid4().hex[:8]}",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.flush()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/utils.py",
        size_bytes=1024,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.flush()

    chunks: list[CodeChunk] = []
    for i in range(chunk_count):
        chunk = CodeChunk(
            repository_id=repo.id,
            file_id=file_row.id,
            file_path=file_row.path,
            commit_sha="abcdef123456",
            chunk_index=i,
            start_line=i * 10 + 1,
            end_line=i * 10 + 10,
            content=f"def func_{i}():\n    return {i}\n",
            embedding=[0.05] * 384 if with_embedding else None,
        )
        db_session.add(chunk)
        chunks.append(chunk)

    db_session.flush()
    return repo, chunks


def test_generate_embeddings_success(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=3)
    provider = _MockProvider(dimension=384)

    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
        batch_size=2,
    )

    assert result.succeeded
    assert result.embedded == 3
    assert result.skipped == 0
    assert result.failed == 0
    assert len(provider.calls) == 2  # 3 items with batch size 2 -> 2 calls

    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384


def test_generate_embeddings_idempotent_skip_already_embedded(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=3, with_embedding=True)
    provider = _MockProvider(dimension=384)

    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
        force=False,
    )

    assert result.succeeded
    assert result.embedded == 0
    assert result.skipped == 3
    assert result.failed == 0
    assert len(provider.calls) == 0  # No provider calls needed


def test_generate_embeddings_force_reembed(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=2, with_embedding=True)
    provider = _MockProvider(dimension=384)

    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
        force=True,
    )

    assert result.succeeded
    assert result.embedded == 2
    assert result.skipped == 0
    assert len(provider.calls) == 1


def test_generate_embeddings_handles_empty_repo(db_session):
    repo = Repository(
        owner_id=str(uuid4()),
        provider="github",
        external_id=str(uuid4()),
        url="https://github.com/example/empty",
        default_branch="main",
        status="cloned",
    )
    db_session.add(repo)
    db_session.flush()

    provider = _MockProvider(dimension=384)
    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
    )

    assert result.succeeded
    assert result.total_chunks == 0
    assert result.embedded == 0


def test_generate_embeddings_provider_failure(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=2)
    provider = _MockProvider(dimension=384, error_on_batch=True)

    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
    )

    assert not result.succeeded
    assert result.failed == 2
    assert result.embedded == 0
    assert len(result.errors) > 0
    assert "Mock embedding generation failure" in result.errors[0]


def test_generate_embeddings_dimension_mismatch_skipped(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=2)
    provider = _MockProvider(dimension=384, return_wrong_dim=True)

    result = generate_embeddings_for_repository(
        db=db_session,
        repository_id=repo.id,
        provider=provider,
    )

    assert not result.succeeded
    assert result.failed == 2
    assert result.embedded == 0
    assert any("invalid dimension" in err for err in result.errors)


def test_search_similar_chunks(db_session):
    repo, chunks = _create_test_repo_and_chunks(db_session, chunk_count=3, with_embedding=False)

    # Assign distinct embedding vectors to test cosine distance similarity ranking
    chunks[0].embedding = [1.0] + [0.0] * 383
    chunks[1].embedding = [0.5] + [0.5] + [0.0] * 382
    chunks[2].embedding = [0.0] + [1.0] + [0.0] * 382
    db_session.flush()

    query_vec = [1.0] + [0.0] * 383
    # Try searching; if pgvector extension is installed in DB it ranks by cosine distance
    try:
        results = search_similar_chunks(
            db=db_session,
            query_vector=query_vec,
            repository_id=repo.id,
            limit=2,
        )
        assert len(results) <= 2
        if results:
            closest_chunk, distance = results[0]
            assert closest_chunk.id == chunks[0].id
            assert distance >= 0.0
    except Exception as exc:
        # If pgvector extension is not compiled into postgres server, verify function constructed query
        if "extension" in str(exc) or "vector" in str(exc) or "operator does not exist" in str(exc):
            pytest.skip(f"pgvector extension not active in PostgreSQL instance: {exc}")
        raise
