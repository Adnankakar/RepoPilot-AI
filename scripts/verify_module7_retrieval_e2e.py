"""
verify_module7_retrieval_e2e.py

End-to-End Verification Script for Module 7: Retrieval Service.

Demonstrates and verifies:
1. Vector similarity search and score calculation.
2. Single-question retrieval of relevant code chunks.
3. Multi-tenant repository authorization boundaries (rejecting unauthorized access).
4. Insufficient-evidence thresholding (identifying and rejecting irrelevant questions).
5. Dynamic threshold overrides per request.
6. Batch question retrieval with shared batch embeddings.
7. REST API endpoint functionality (/api/retrieval/query and /api/retrieval/batch).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.database import SessionLocal
from app.main import app
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_file import RepositoryFile
from app.models.user import User, UserRole
from app.services.embedding_provider import EmbeddingProvider
from app.services.retrieval_service import (
    UnauthorizedRepositoryAccessError,
    batch_retrieve_relevant_chunks,
    execute_vector_similarity_search,
    retrieve_relevant_chunks,
)


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for repeatable verification."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension
        self.preset_vectors: dict[str, list[float]] = {}
        self.default_vector = [0.0] * dimension
        self.default_vector[0] = 0.1

    @property
    def dimension(self) -> int:
        return self._dimension

    def register(self, text: str, vector: list[float]) -> None:
        self.preset_vectors[text] = vector

    def embed(self, text: str) -> list[float]:
        return self.preset_vectors.get(text, self.default_vector)

    def embed_batch(self, texts) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def run_all_verifications():
    print("=" * 80)
    print("REPOPILOT AI - MODULE 7: RETRIEVAL SERVICE E2E VERIFICATION")
    print("=" * 80)

    db = SessionLocal()
    provider = DeterministicEmbeddingProvider(dimension=384)

    try:
        # -------------------------------------------------------------------
        # Setup: Users and Repositories
        # -------------------------------------------------------------------
        print("\n[SETUP] Creating test users and isolated repositories...")
        user_alice = User(
            email=f"alice_{uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            role=UserRole.DEVELOPER,
        )
        user_bob = User(
            email=f"bob_{uuid4().hex[:6]}@example.com",
            password_hash="fakehash",
            role=UserRole.DEVELOPER,
        )
        db.add_all([user_alice, user_bob])
        db.commit()

        alice_id = str(user_alice.id)
        bob_id = str(user_bob.id)

        # Alice's Repository: Authentication and Security
        repo_alice = Repository(
            owner_id=alice_id,
            provider="github",
            external_id=str(uuid4()),
            url=f"https://github.com/alice/auth-service-{uuid4().hex[:4]}",
            default_branch="main",
            status="completed",
        )
        db.add(repo_alice)
        db.commit()

        file_alice = RepositoryFile(
            repository_id=repo_alice.id,
            path="src/security/jwt.py",
            size_bytes=450,
            extension=".py",
            encoding="utf-8",
        )
        db.add(file_alice)
        db.commit()

        # Vector along axis 0
        v_auth = [1.0] + [0.0] * 383
        chunk_alice_auth = CodeChunk(
            repository_id=repo_alice.id,
            file_id=file_alice.id,
            file_path=file_alice.path,
            commit_sha="alice_commit_1",
            chunk_index=0,
            start_line=1,
            end_line=20,
            content="def verify_jwt_token(token: str) -> dict:\n    return jwt.decode(token, SECRET_KEY)\n",
            embedding=v_auth,
        )
        # Vector along axis 1
        v_db = [0.0, 1.0] + [0.0] * 382
        chunk_alice_db = CodeChunk(
            repository_id=repo_alice.id,
            file_id=file_alice.id,
            file_path="src/security/db.py",
            commit_sha="alice_commit_1",
            chunk_index=1,
            start_line=21,
            end_line=40,
            content="def get_user_by_id(db: Session, user_id: str) -> User:\n    return db.get(User, user_id)\n",
            embedding=v_db,
        )
        db.add_all([chunk_alice_auth, chunk_alice_db])
        db.commit()

        # Bob's Repository: Secret Trading Algorithms (Private to Bob)
        repo_bob = Repository(
            owner_id=bob_id,
            provider="github",
            external_id=str(uuid4()),
            url=f"https://github.com/bob/trading-bot-{uuid4().hex[:4]}",
            default_branch="main",
            status="completed",
        )
        db.add(repo_bob)
        db.commit()

        file_bob = RepositoryFile(
            repository_id=repo_bob.id,
            path="models/alpha.py",
            size_bytes=600,
            extension=".py",
            encoding="utf-8",
        )
        db.add(file_bob)
        db.commit()

        # Vector along axis 0 (same direction as auth, but in Bob's private repo)
        chunk_bob_secret = CodeChunk(
            repository_id=repo_bob.id,
            file_id=file_bob.id,
            file_path=file_bob.path,
            commit_sha="bob_commit_1",
            chunk_index=0,
            start_line=1,
            end_line=15,
            content="def calculate_alpha(prices: list[float]) -> float:\n    # Bob's confidential hedge fund secret\n    return sum(prices) / len(prices)\n",
            embedding=v_auth,
        )
        db.add(chunk_bob_secret)
        db.commit()

        print(f"  Alice User ID: {alice_id} (Repo: {repo_alice.id})")
        print(f"  Bob User ID:   {bob_id} (Repo: {repo_bob.id})")

        # -------------------------------------------------------------------
        # Flow 1: Vector Similarity Search
        # -------------------------------------------------------------------
        print("\n[FLOW 1] Testing Vector Similarity Search & Distance Calculation...")
        query_v = [1.0] + [0.0] * 383
        raw_candidates = execute_vector_similarity_search(
            db=db,
            query_vector=query_v,
            repository_ids=[repo_alice.id],
            limit=5,
        )
        assert len(raw_candidates) == 2
        assert raw_candidates[0].id == chunk_alice_auth.id
        assert abs(raw_candidates[0].similarity - 1.0) < 1e-4
        assert abs(raw_candidates[0].distance - 0.0) < 1e-4
        print(f"  Rank 1 Chunk: {raw_candidates[0].file_path} (similarity={raw_candidates[0].similarity:.4f}, distance={raw_candidates[0].distance:.4f})")
        print(f"  Rank 2 Chunk: {raw_candidates[1].file_path} (similarity={raw_candidates[1].similarity:.4f}, distance={raw_candidates[1].distance:.4f})")
        print("  ✓ Vector similarity correctly ordered by descending similarity score.")

        # -------------------------------------------------------------------
        # Flow 2: Question Retrieval (High Relevance Match)
        # -------------------------------------------------------------------
        print("\n[FLOW 2] Testing Question Retrieval for High Relevance Query...")
        question_auth = "How do we decode and verify JWT tokens?"
        provider.register(question_auth, [1.0] + [0.0] * 383)

        result_auth = retrieve_relevant_chunks(
            db=db,
            question=question_auth,
            user=alice_id,
            repository_id=repo_alice.id,
            similarity_threshold=0.50,
            provider=provider,
        )
        assert result_auth.has_sufficient_evidence is True
        assert len(result_auth.chunks) >= 1
        assert result_auth.chunks[0].id == chunk_alice_auth.id
        print(f"  Query: '{question_auth}'")
        print(f"  Evidence: {result_auth.has_sufficient_evidence} (Best score: {result_auth.best_score:.4f}, Threshold: {result_auth.threshold})")
        print(f"  Retrieved Chunk #1: {result_auth.chunks[0].file_path} Lines {result_auth.chunks[0].start_line}-{result_auth.chunks[0].end_line}")
        print("  ✓ Highly relevant question retrieved matching chunk with sufficient evidence.")

        # -------------------------------------------------------------------
        # Flow 3: Multi-tenant Repository Authorization Boundaries
        # -------------------------------------------------------------------
        print("\n[FLOW 3] Testing Repository Authorization & Cross-Tenant Isolation...")
        # Alice searching across all her repositories should NEVER see Bob's code
        search_all_alice = retrieve_relevant_chunks(
            db=db,
            question=question_auth,
            user=alice_id,
            provider=provider,
        )
        for c in search_all_alice.chunks:
            assert c.repository_id == repo_alice.id
            assert c.repository_id != repo_bob.id
        print("  ✓ Alice searching unspecified repositories only searched Alice's repositories.")

        # Alice trying to explicitly search Bob's repo MUST raise UnauthorizedRepositoryAccessError
        try:
            retrieve_relevant_chunks(
                db=db,
                question="Show me the trading secrets",
                user=alice_id,
                repository_id=repo_bob.id,
                provider=provider,
            )
            assert False, "Should have raised UnauthorizedRepositoryAccessError"
        except UnauthorizedRepositoryAccessError as exc:
            print(f"  ✓ Access denied to Bob's repository: {exc}")

        # -------------------------------------------------------------------
        # Flow 4: Insufficient-Evidence Thresholding
        # -------------------------------------------------------------------
        print("\n[FLOW 4] Testing Insufficient-Evidence Thresholding...")
        question_unrelated = "What is the best chocolate cake recipe?"
        # Vector orthogonal to all Alice's code
        v_unrelated = [0.0] * 50 + [1.0] + [0.0] * 333
        provider.register(question_unrelated, v_unrelated)

        result_unrelated = retrieve_relevant_chunks(
            db=db,
            question=question_unrelated,
            user=alice_id,
            repository_id=repo_alice.id,
            similarity_threshold=0.50,
            provider=provider,
        )
        assert result_unrelated.has_sufficient_evidence is False
        assert len(result_unrelated.chunks) == 0
        assert result_unrelated.insufficient_evidence_reason is not None
        print(f"  Query: '{question_unrelated}'")
        print(f"  Evidence: {result_unrelated.has_sufficient_evidence}")
        print(f"  Filtered chunks: {len(result_unrelated.chunks)} (Raw candidates: {len(result_unrelated.all_candidates)})")
        print(f"  Reason: {result_unrelated.insufficient_evidence_reason}")
        print("  ✓ Irrelevant query correctly rejected with has_sufficient_evidence=False.")

        # -------------------------------------------------------------------
        # Flow 5: Dynamic Threshold Parameter Overrides
        # -------------------------------------------------------------------
        print("\n[FLOW 5] Testing Dynamic Threshold Parameter Overrides...")
        question_partial = "Find database user lookup"
        # 45 degree angle between auth and db -> cosine similarity ~ 0.707 to db
        v_partial = [0.7071, 0.7071] + [0.0] * 382
        provider.register(question_partial, v_partial)

        # Strict threshold 0.85 -> rejected
        strict_res = retrieve_relevant_chunks(
            db=db,
            question=question_partial,
            user=alice_id,
            repository_id=repo_alice.id,
            similarity_threshold=0.85,
            provider=provider,
        )
        assert strict_res.has_sufficient_evidence is False

        # Lenient threshold 0.60 -> accepted
        lenient_res = retrieve_relevant_chunks(
            db=db,
            question=question_partial,
            user=alice_id,
            repository_id=repo_alice.id,
            similarity_threshold=0.60,
            provider=provider,
        )
        assert lenient_res.has_sufficient_evidence is True
        print(f"  Best score: {lenient_res.best_score:.4f}")
        print(f"  Strict threshold (0.85): Evidence = {strict_res.has_sufficient_evidence}")
        print(f"  Lenient threshold (0.60): Evidence = {lenient_res.has_sufficient_evidence}")
        print("  ✓ Dynamic threshold override works accurately.")

        # -------------------------------------------------------------------
        # Flow 6: Batch Question Retrieval
        # -------------------------------------------------------------------
        print("\n[FLOW 6] Testing Batch Question Retrieval...")
        batch_questions = [
            question_auth,
            question_unrelated,
            question_partial,
        ]
        batch_results = batch_retrieve_relevant_chunks(
            db=db,
            questions=batch_questions,
            user=alice_id,
            repository_id=repo_alice.id,
            similarity_threshold=0.50,
            provider=provider,
        )
        assert len(batch_results) == 3
        assert batch_results[0].has_sufficient_evidence is True
        assert batch_results[1].has_sufficient_evidence is False
        assert batch_results[2].has_sufficient_evidence is True
        print(f"  Processed {len(batch_results)} questions in batch:")
        for idx, br in enumerate(batch_results):
            print(f"    Q{idx+1} ('{br.question}'): evidence={br.has_sufficient_evidence}, chunks={len(br.chunks)}")
        print("  ✓ Batch question retrieval successfully evaluated all queries.")

        # -------------------------------------------------------------------
        # Flow 7: REST API Endpoint Verification
        # -------------------------------------------------------------------
        print("\n[FLOW 7] Testing FastAPI REST Endpoints...")
        alice_token = create_access_token(user_alice.id)
        client = TestClient(app)

        with patch("app.services.retrieval_service.get_embedding_provider", return_value=provider):
            # 7a. Single Query endpoint
            api_res = client.post(
                "/api/retrieval/query",
                headers={"Authorization": f"Bearer {alice_token}"},
                json={
                    "question": question_auth,
                    "repository_id": repo_alice.id,
                    "top_k": 5,
                    "similarity_threshold": 0.50,
                },
            )
            assert api_res.status_code == 200, f"Expected 200, got {api_res.status_code}: {api_res.text}"
            api_data = api_res.json()
            assert api_data["has_sufficient_evidence"] is True
            assert len(api_data["chunks"]) >= 1
            print("  ✓ POST /api/retrieval/query returned 200 OK with serialized chunks.")

            # 7b. Unauthorized Repository -> 403 Forbidden
            forbidden_res = client.post(
                "/api/retrieval/query",
                headers={"Authorization": f"Bearer {alice_token}"},
                json={
                    "question": question_auth,
                    "repository_id": repo_bob.id,
                },
            )
            assert forbidden_res.status_code == 403
            print(f"  ✓ POST /api/retrieval/query unauthorized repo correctly returned 403: {forbidden_res.json()['detail']}")

            # 7c. Batch Query endpoint
            batch_api_res = client.post(
                "/api/retrieval/batch",
                headers={"Authorization": f"Bearer {alice_token}"},
                json={
                    "questions": [question_auth, question_unrelated],
                    "repository_id": repo_alice.id,
                    "similarity_threshold": 0.50,
                },
            )
            assert batch_api_res.status_code == 200, f"Expected 200, got {batch_api_res.status_code}: {batch_api_res.text}"
            batch_api_data = batch_api_res.json()
            assert batch_api_data["total_questions"] == 2
            assert batch_api_data["questions_with_evidence"] == 1
            print("  ✓ POST /api/retrieval/batch returned 200 OK with batch results summary.")

        print("\n" + "=" * 80)
        print("ALL 7 MODULE 7 RETRIEVAL SERVICE VERIFICATIONS PASSED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    run_all_verifications()
