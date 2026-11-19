"""
test_retrieval_api.py

API integration tests for Retrieval Service endpoints:
- POST /api/retrieval/query
- POST /api/retrieval/batch
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.user import User, UserRole
from tests.test_retrieval_service import MockEmbeddingProvider


def _create_test_user(db_session) -> tuple[User, str]:
    """Helper to create and commit a test user, returning (user, token)."""
    user = User(
        email=f"retrieval_user_{uuid4().hex[:8]}@example.com",
        password_hash="fakehash",
        role=UserRole.DEVELOPER,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id)
    return user, token


def _seed_test_repo(db_session, owner_id: str) -> tuple[Repository, list[CodeChunk]]:
    """Seed repository with test code chunks."""
    repo = Repository(
        owner_id=owner_id,
        provider="github",
        external_id=str(uuid4()),
        url=f"https://github.com/org/{uuid4().hex[:6]}",
        default_branch="main",
        status="completed",
    )
    db_session.add(repo)
    db_session.commit()

    file_row = RepositoryFile(
        repository_id=repo.id,
        path="src/auth.py",
        size_bytes=300,
        extension=".py",
        encoding="utf-8",
    )
    db_session.add(file_row)
    db_session.commit()

    chunk = CodeChunk(
        repository_id=repo.id,
        file_id=file_row.id,
        file_path=file_row.path,
        commit_sha="c12345",
        chunk_index=0,
        start_line=1,
        end_line=10,
        content="def verify_jwt_token(token: str) -> bool:\n    return True\n",
        embedding=[1.0] + [0.0] * 383,
    )
    db_session.add(chunk)
    db_session.commit()
    return repo, [chunk]


def test_query_retrieval_unauthenticated(test_client):
    """Calling retrieval endpoint without bearer token returns 401 Unauthorized."""
    res = test_client.post(
        "/api/retrieval/query",
        json={"question": "How to verify JWT?"},
    )
    assert res.status_code == 401


def test_query_retrieval_success_with_evidence(test_client, db_session):
    """Authenticated user queries their repository and retrieves matching chunk."""
    user, token = _create_test_user(db_session)
    repo, chunks = _seed_test_repo(db_session, owner_id=str(user.id))

    mock_provider = MockEmbeddingProvider(dimension=384)
    # Query vector matches chunk embedding
    mock_provider.set_vector_for_text("How to verify JWT?", [1.0] + [0.0] * 383)

    with patch("app.services.retrieval_service.get_embedding_provider", return_value=mock_provider):
        res = test_client.post(
            "/api/retrieval/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How to verify JWT?",
                "repository_id": repo.id,
                "top_k": 3,
                "similarity_threshold": 0.50,
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["question"] == "How to verify JWT?"
    assert data["has_sufficient_evidence"] is True
    assert len(data["chunks"]) == 1
    chunk_res = data["chunks"][0]
    assert chunk_res["id"] == chunks[0].id
    assert chunk_res["file_path"] == "src/auth.py"
    assert chunk_res["similarity"] == 1.0
    assert chunk_res["distance"] == 0.0
    assert repo.id in data["searched_repositories"]


def test_query_retrieval_insufficient_evidence(test_client, db_session):
    """When query similarity is below threshold, returns 200 with has_sufficient_evidence=False."""
    user, token = _create_test_user(db_session)
    repo, _ = _seed_test_repo(db_session, owner_id=str(user.id))

    mock_provider = MockEmbeddingProvider(dimension=384)
    # Orthogonal query vector
    mock_provider.set_vector_for_text("Unrelated cooking recipe", [0.0] * 100 + [1.0] + [0.0] * 283)

    with patch("app.services.retrieval_service.get_embedding_provider", return_value=mock_provider):
        res = test_client.post(
            "/api/retrieval/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Unrelated cooking recipe",
                "repository_id": repo.id,
                "similarity_threshold": 0.50,
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["has_sufficient_evidence"] is False
    assert len(data["chunks"]) == 0
    assert data["insufficient_evidence_reason"] is not None
    assert "No chunks met the similarity threshold" in data["insufficient_evidence_reason"]


def test_query_retrieval_unauthorized_repository_forbidden(test_client, db_session):
    """Querying a repository owned by a different user returns 403 Forbidden."""
    user_a, token_a = _create_test_user(db_session)
    user_b, _ = _create_test_user(db_session)

    # Repository owned by User B
    repo_b, _ = _seed_test_repo(db_session, owner_id=str(user_b.id))

    # User A attempts to search User B's repository
    res = test_client.post(
        "/api/retrieval/query",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "question": "What is in user B's repository?",
            "repository_id": repo_b.id,
        },
    )

    assert res.status_code == 403
    assert "not authorized" in res.json()["detail"].lower()


def test_query_retrieval_validation_empty_question(test_client, db_session):
    """Empty question fails schema validation with 422."""
    user, token = _create_test_user(db_session)
    res = test_client.post(
        "/api/retrieval/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": ""},
    )
    assert res.status_code == 422


def test_query_retrieval_validation_negative_top_k(test_client, db_session):
    """Negative top_k fails schema validation with 422."""
    user, token = _create_test_user(db_session)
    res = test_client.post(
        "/api/retrieval/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Valid question", "top_k": -1},
    )
    assert res.status_code == 422


def test_query_retrieval_validation_threshold_out_of_range(test_client, db_session):
    """Similarity threshold outside [0, 1] fails schema validation with 422."""
    user, token = _create_test_user(db_session)
    res = test_client.post(
        "/api/retrieval/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Valid question", "similarity_threshold": 1.5},
    )
    assert res.status_code == 422


def test_batch_query_retrieval(test_client, db_session):
    """Batch query endpoint processes multiple questions."""
    user, token = _create_test_user(db_session)
    repo, chunks = _seed_test_repo(db_session, owner_id=str(user.id))

    mock_provider = MockEmbeddingProvider(dimension=384)
    mock_provider.set_vector_for_text("Question 1", [1.0] + [0.0] * 383)
    mock_provider.set_vector_for_text("Question 2", [0.0] * 50 + [1.0] + [0.0] * 333)

    with patch("app.services.retrieval_service.get_embedding_provider", return_value=mock_provider):
        res = test_client.post(
            "/api/retrieval/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "questions": ["Question 1", "Question 2"],
                "repository_id": repo.id,
                "similarity_threshold": 0.50,
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["total_questions"] == 2
    assert data["questions_with_evidence"] == 1
    assert len(data["results"]) == 2
    assert data["results"][0]["has_sufficient_evidence"] is True
    assert data["results"][1]["has_sufficient_evidence"] is False


def test_batch_query_retrieval_unauthorized(test_client, db_session):
    """Batch endpoint returns 403 when requesting an unauthorized repository."""
    user_a, token_a = _create_test_user(db_session)
    user_b, _ = _create_test_user(db_session)

    repo_b, _ = _seed_test_repo(db_session, owner_id=str(user_b.id))

    res = test_client.post(
        "/api/retrieval/batch",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "questions": ["Question A", "Question B"],
            "repository_id": repo_b.id,
        },
    )

    assert res.status_code == 403
    assert "not authorized" in res.json()["detail"].lower()
