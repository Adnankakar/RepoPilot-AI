"""
chat.py

Pydantic schemas for the LLM-powered Chat / Q&A endpoint.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatAskRequest(BaseModel):
    """Request payload for the LLM-powered Q&A endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        description="Natural-language question about the indexed codebase.",
        examples=["How is JWT authentication implemented?"],
    )
    repository_id: str | None = Field(
        default=None,
        description="Scope the search to a single repository ID.",
    )
    repository_ids: list[str] | None = Field(
        default=None,
        description="Scope the search to multiple repository IDs.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of code chunks to retrieve as evidence.",
    )
    similarity_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity to treat a chunk as evidence (default from config).",
    )

    model_config = ConfigDict(extra="forbid")


class ChatAskResponse(BaseModel):
    """Response from the LLM-powered Q&A endpoint."""

    question: str = Field(..., description="The original question.")
    answer: str | None = Field(
        default=None,
        description="LLM-generated natural-language answer grounded in retrieved code, "
                    "or null when there is insufficient evidence.",
    )
    has_sufficient_evidence: bool = Field(
        ...,
        description="True when at least one chunk met the similarity threshold.",
    )
    insufficient_evidence_reason: str | None = Field(
        default=None,
        description="Human-readable reason when has_sufficient_evidence is False.",
    )
    best_score: float | None = Field(
        default=None,
        description="Highest similarity score among retrieved chunks.",
    )
    threshold: float = Field(..., description="Similarity threshold that was applied.")
    chunks_used: int = Field(
        default=0,
        description="Number of code chunks included in the LLM context.",
    )
    searched_repositories: list[str] = Field(
        default_factory=list,
        description="Repository IDs that were searched.",
    )

    model_config = ConfigDict(from_attributes=True)
