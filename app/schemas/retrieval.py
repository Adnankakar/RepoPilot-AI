"""
retrieval.py

Pydantic schemas for the Retrieval Service API.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievalQueryRequest(BaseModel):
    """Request payload for retrieving code chunks relevant to a question."""

    question: str = Field(
        ...,
        min_length=1,
        description="The user question or search query to find relevant chunks for.",
        examples=["How is JWT authentication implemented?"],
    )
    repository_id: str | None = Field(
        default=None,
        description="Optional single repository ID to scope the search to.",
    )
    repository_ids: list[str] | None = Field(
        default=None,
        description="Optional collection of repository IDs to scope the search to.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of relevant chunks to return.",
    )
    similarity_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Custom cosine similarity threshold (0.0 to 1.0) override.",
    )

    model_config = ConfigDict(extra="forbid")


class BatchRetrievalQueryRequest(BaseModel):
    """Request payload for retrieving code chunks for multiple questions in batch."""

    questions: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of questions to search relevant chunks for in batch.",
    )
    repository_id: str | None = Field(
        default=None,
        description="Optional single repository ID filter.",
    )
    repository_ids: list[str] | None = Field(
        default=None,
        description="Optional list of repository IDs to filter by.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of relevant chunks to return per question.",
    )
    similarity_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Custom cosine similarity threshold override.",
    )

    model_config = ConfigDict(extra="forbid")


class RetrievedChunkResponse(BaseModel):
    """Serialized representation of a retrieved code chunk with similarity score."""

    id: str = Field(..., description="Unique ID of the code chunk.")
    repository_id: str = Field(..., description="ID of the repository containing this chunk.")
    file_path: str = Field(..., description="Relative file path within the repository.")
    chunk_index: int = Field(..., description="0-indexed sequence of this chunk in the file.")
    start_line: int = Field(..., description="1-indexed starting line number.")
    end_line: int = Field(..., description="1-indexed ending line number.")
    content: str = Field(..., description="Source code or text content of the chunk.")
    similarity: float = Field(
        ...,
        description="Cosine similarity score between query and chunk (higher = more relevant).",
    )
    distance: float = Field(
        ...,
        description="Raw pgvector cosine distance (lower = closer).",
    )
    commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA associated with the indexed chunk.",
    )

    model_config = ConfigDict(from_attributes=True)


class RetrievalResponse(BaseModel):
    """Response containing retrieved chunks and evidence assessment."""

    question: str = Field(..., description="The query that was executed.")
    has_sufficient_evidence: bool = Field(
        ...,
        description="True if at least one chunk met or exceeded the similarity threshold.",
    )
    threshold: float = Field(
        ...,
        description="The similarity threshold that was applied.",
    )
    best_score: float | None = Field(
        default=None,
        description="Highest similarity score among retrieved chunks (None if no chunks exist).",
    )
    chunks: list[RetrievedChunkResponse] = Field(
        default_factory=list,
        description="Ranked list of relevant chunks passing the similarity threshold.",
    )
    searched_repositories: list[str] = Field(
        default_factory=list,
        description="List of authorized repository IDs that were searched.",
    )
    insufficient_evidence_reason: str | None = Field(
        default=None,
        description="Human-readable explanation if evidence was insufficient.",
    )
    message: str = Field(
        default="Retrieval completed.",
        description="Status message summarizing the retrieval result.",
    )

    model_config = ConfigDict(from_attributes=True)


class BatchRetrievalResponse(BaseModel):
    """Response containing batch retrieval results across multiple questions."""

    results: list[RetrievalResponse] = Field(
        default_factory=list,
        description="Retrieval result for each submitted question.",
    )
    total_questions: int = Field(..., description="Number of questions processed.")
    questions_with_evidence: int = Field(
        ...,
        description="Number of questions for which sufficient evidence was found.",
    )

    model_config = ConfigDict(from_attributes=True)
