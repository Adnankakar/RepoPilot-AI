"""
embedding_service.py

Embedding generation pipeline and vector similarity search for CodeChunk records.

Fetches code chunks from the database, generates vector embeddings in
configurable batches using an EmbeddingProvider, validates vector dimensions,
and stores the vectors back on each chunk's pgvector ``embedding`` column —
preserving all repository, file, commit, and line metadata (only the
``embedding`` column is updated, in place).

Also provides similarity search using pgvector cosine distance queries.

Design:
- Reuses the existing CodeChunk model and its pgvector ``embedding`` column;
  no new tables or columns are introduced.
- Idempotent / resumable: by default only chunks whose embedding is NULL are
  fetched (``force=False``), so repeated runs never re-embed or duplicate work.
- Batches: chunks are embedded ``batch_size`` at a time so the provider can
  vectorise efficiently and memory stays bounded.
- Dimension validation: every generated vector must match ``provider.dimension``
  before it is assigned; mismatched vectors are skipped and recorded.
- Safe failure handling: provider (EmbeddingError) and count-mismatch failures
  are caught per batch, logged, and recorded so a single bad batch does not
  abort the whole run. This service does not commit or flush; the caller is
  responsible for persisting (run_pipeline wraps it in a savepoint so a database
  failure during embedding never corrupts the already-stored chunks).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.services.embedding_provider import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Summary of one embedding run for a repository."""

    repository_id: str
    # All chunks that belong to the repository (for context).
    total_chunks: int = 0
    # Chunks that received a vector this run.
    embedded: int = 0
    # Chunks that already had an embedding and were skipped (NULL-filter).
    skipped: int = 0
    # Chunks that errored or failed dimension validation.
    failed: int = 0
    # Human-readable error messages (bounded to keep logs compact).
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.failed == 0


def generate_embeddings_for_repository(
    db: Session,
    repository_id: str,
    provider: EmbeddingProvider | None = None,
    batch_size: int | None = None,
    force: bool = False,
) -> EmbeddingResult:
    """
    Generate and assign embeddings for the code chunks of a repository.

    Parameters:
        db: Active SQLAlchemy session. This function does not commit; the
            caller persists the assigned embeddings (e.g. run_pipeline wraps
            the call in a savepoint).
        repository_id: Repository whose chunks should be embedded.
        provider: EmbeddingProvider to use. Defaults to the shared
            provider (lazy-loaded, cached).
        batch_size: Chunks embedded per provider call. Defaults to
            settings.embedding_batch_size.
        force: If False (default), only chunks whose embedding is NULL are
            processed — repeated runs skip already-embedded chunks. If True,
            every chunk is re-embedded.

    Returns:
        An EmbeddingResult with embedded / skipped / failed counts and errors.
    """
    provider = provider or get_embedding_provider()
    if batch_size is None:
        batch_size = settings.embedding_batch_size
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer.")

    all_count = (
        db.scalar(
            select(func.count())
            .select_from(CodeChunk)
            .where(CodeChunk.repository_id == repository_id)
        )
        or 0
    )

    stmt = select(CodeChunk).where(CodeChunk.repository_id == repository_id)
    if not force:
        stmt = stmt.where(CodeChunk.embedding.is_(None))
    stmt = stmt.order_by(CodeChunk.file_path, CodeChunk.chunk_index)
    chunks = list(db.scalars(stmt).all())

    result = EmbeddingResult(
        repository_id=repository_id,
        total_chunks=all_count,
        skipped=(all_count - len(chunks)) if not force else 0,
    )

    if not chunks:
        logger.info(
            "No chunks require embedding for repository %s (total=%d).",
            repository_id,
            all_count,
        )
        return result

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        _embed_batch(batch, provider, result)

    logger.info(
        "Embedding run for repository %s: embedded=%d skipped=%d failed=%d total=%d",
        repository_id,
        result.embedded,
        result.skipped,
        result.failed,
        result.total_chunks,
    )
    return result


def _embed_batch(
    batch: list[CodeChunk],
    provider: EmbeddingProvider,
    result: EmbeddingResult,
) -> None:
    """Embed one batch of chunks, validating dimensions and recording failures."""
    contents = [c.content for c in batch]

    try:
        vectors = provider.embed_batch(contents)
    except EmbeddingError as exc:
        logger.warning(
            "Provider error embedding batch of %d chunks: %s", len(batch), exc
        )
        result.failed += len(batch)
        result.errors.append(f"provider error: {exc}")
        return

    if len(vectors) != len(batch):
        msg = (
            f"provider returned {len(vectors)} vectors for {len(batch)} chunks"
        )
        logger.warning(msg)
        result.failed += len(batch)
        result.errors.append(msg)
        return

    expected_dim = provider.dimension
    for chunk, vec in zip(batch, vectors):
        if vec is None or len(vec) != expected_dim:
            actual = None if vec is None else len(vec)
            logger.warning(
                "Skipping chunk %s: embedding dimension %s != %d",
                chunk.id,
                actual,
                expected_dim,
            )
            result.failed += 1
            result.errors.append(
                f"invalid dimension for chunk {chunk.id}: {actual} (expected {expected_dim})"
            )
            continue
        chunk.embedding = [float(x) for x in vec]
        result.embedded += 1


def _cosine_distance(u: list[float], v: list[float]) -> float:
    """Compute cosine distance between two float vectors in Python."""
    dot = 0.0
    norm_u = 0.0
    norm_v = 0.0
    for a, b in zip(u, v):
        dot += a * b
        norm_u += a * a
        norm_v += b * b
    if norm_u <= 0.0 or norm_v <= 0.0:
        return 1.0
    sim = dot / (math.sqrt(norm_u) * math.sqrt(norm_v))
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _search_similar_chunks_fallback(
    db: Session,
    query_vector: list[float],
    repository_ids: Sequence[str] | None = None,
    limit: int = 10,
) -> list[tuple[CodeChunk, float]]:
    """In-memory cosine distance fallback when pgvector is not available in database."""
    stmt = select(CodeChunk).where(CodeChunk.embedding.is_not(None))
    if repository_ids is not None:
        if len(repository_ids) == 1:
            stmt = stmt.where(CodeChunk.repository_id == repository_ids[0])
        else:
            stmt = stmt.where(CodeChunk.repository_id.in_(list(repository_ids)))

    chunks = list(db.scalars(stmt).all())
    scored: list[tuple[CodeChunk, float]] = []
    for c in chunks:
        if c.embedding is not None:
            vec = [float(x) for x in c.embedding]
            if len(vec) != len(query_vector):
                logger.warning(
                    "Skipping chunk %s with dimension %d != query dimension %d (mismatched embedding model; re-embedding required).",
                    c.id,
                    len(vec),
                    len(query_vector),
                )
                continue
            dist = _cosine_distance(query_vector, vec)
            scored.append((c, dist))

    scored.sort(key=lambda item: item[1])
    return scored[:limit]


def search_similar_chunks(
    db: Session,
    query_vector: list[float],
    repository_id: str | None = None,
    repository_ids: Sequence[str] | None = None,
    limit: int = 10,
) -> list[tuple[CodeChunk, float]]:
    """
    Search for stored code chunks most similar to a query vector using pgvector cosine distance,
    with an automatic in-memory fallback if the pgvector extension is not compiled into the database.

    Parameters:
        db: Active SQLAlchemy session.
        query_vector: Dense vector representing the search query.
        repository_id: Optional single repository filter (legacy / shorthand).
        repository_ids: Optional collection of repository IDs to filter chunks by.
        limit: Maximum number of chunks to return.

    Returns:
        List of tuples: (CodeChunk, cosine_distance) sorted in ascending order of distance
        (smallest distance = highest semantic similarity).
    """
    target_repo_ids: list[str] | None = None
    if repository_ids is not None:
        target_repo_ids = list(repository_ids)
    elif repository_id is not None:
        target_repo_ids = [repository_id]

    try:
        with db.begin_nested():
            distance = CodeChunk.embedding.cosine_distance(query_vector)
            stmt = (
                select(CodeChunk, distance.label("distance"))
                .where(CodeChunk.embedding.is_not(None))
            )
            if target_repo_ids is not None:
                if len(target_repo_ids) == 1:
                    stmt = stmt.where(CodeChunk.repository_id == target_repo_ids[0])
                else:
                    stmt = stmt.where(CodeChunk.repository_id.in_(target_repo_ids))

            stmt = stmt.order_by(distance).limit(limit)
            rows = db.execute(stmt).all()
            return [(chunk, float(dist)) for chunk, dist in rows]
    except Exception as exc:
        err_msg = str(exc).lower()
        if (
            "vector" in err_msg
            or "operator does not exist" in err_msg
            or "extension" in err_msg
            or "no such function" in err_msg
            or "syntax error" in err_msg
        ):
            logger.info(
                "pgvector distance query not available in database (%s); using in-memory vector similarity fallback.",
                exc,
            )
            return _search_similar_chunks_fallback(
                db=db,
                query_vector=query_vector,
                repository_ids=target_repo_ids,
                limit=limit,
            )
        raise
