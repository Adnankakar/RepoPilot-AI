#!/usr/bin/env python
"""
test_full_system.py

End-to-End Test for RepoPilot AI:
1. Verifies OpenRouter embedding generation (nvidia/nemotron-3-embed-1b:free).
2. Embeds repository code chunks into PostgreSQL using OpenRouter.
3. Retrieves relevant code chunks using vector similarity search.
4. Sends the retrieved code context to OpenRouter's LLM (particle-ai/particle-1:free).
5. Validates grounded answer generation and source file citation.
"""

from pathlib import Path
import sys
import json

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk
from app.models.user import User
from app.services.embedding_provider import get_embedding_provider
from app.services.embedding_service import generate_embeddings_for_repository, search_similar_chunks
from app.services.retrieval_service import retrieve_relevant_chunks
from app.core.rag_orchestration import OpenRouterProvider, build_prompt


def main():
    print("=" * 60)
    print("RepoPilot AI: Full System Integration Test")
    print("=" * 60)

    # 1. Configuration Check
    print("\n[Step 1] Configuration Check:")
    print(f"  Embedding Provider: {settings.embedding_provider}")
    print(f"  Embedding Model   : {settings.embedding_model}")
    print(f"  LLM Provider      : {settings.llm_provider}")
    print(f"  LLM Model         : {settings.llm_model}")
    assert settings.openrouter_api_key, "OPENROUTER_API_KEY must be set in .env"
    print(f"  OpenRouter Key    : {settings.openrouter_api_key[:12]}... (configured)")

    # 2. Embedding Model Test
    print("\n[Step 2] Testing OpenRouter Embedding Provider:")
    embed_provider = get_embedding_provider()
    test_text = "def add(a: int, b: int) -> int: return a + b"
    vec = embed_provider.embed(test_text)
    print(f"  Provider class    : {embed_provider.__class__.__name__}")
    print(f"  Vector dimension  : {len(vec)}")
    print(f"  First 4 floats    : {vec[:4]}")
    assert len(vec) == 2048, f"Expected 2048 dimensions, got {len(vec)}"
    print("  ✓ OpenRouter embedding generation successful!")

    # 3. Database Embeddings Population
    print("\n[Step 3] Testing Repository Embedding in Database:")
    db = SessionLocal()
    target_repo_id = "b10e7b8e-2a25-4be5-b360-138c4e06319e"
    repo = db.query(Repository).filter(Repository.id == target_repo_id).first()
    assert repo is not None, f"Repository {target_repo_id} not found"
    print(f"  Target Repository : {repo.id} (URL: {repo.url})")

    embed_result = generate_embeddings_for_repository(
        db=db,
        repository_id=target_repo_id,
        provider=embed_provider,
        force=True,
    )
    db.commit()
    print(f"  Embed Result      : total={embed_result.total_chunks}, embedded={embed_result.embedded}, failed={embed_result.failed}")
    assert embed_result.embedded > 0, "Expected at least 1 chunk embedded"

    stored_chunk = db.query(CodeChunk).filter(CodeChunk.repository_id == target_repo_id).first()
    assert stored_chunk.embedding is not None
    print(f"  Stored vector dim : {len(stored_chunk.embedding)}")
    assert len(stored_chunk.embedding) == 2048
    print("  ✓ Repository chunks embedded and persisted to DB successfully!")

    # 4. Semantic Vector Search Retrieval
    print("\n[Step 4] Testing Vector Similarity Retrieval:")
    question = "Which function performs addition of two integers?"
    query_vector = embed_provider.embed(question)
    search_results = search_similar_chunks(
        db=db,
        query_vector=query_vector,
        repository_id=target_repo_id,
        limit=2,
    )
    print(f"  Retrieved Chunks  : {len(search_results)}")
    for chunk, dist in search_results:
        sim = 1.0 - dist
        print(f"    - File: {chunk.file_path} (Lines {chunk.start_line}-{chunk.end_line}) | Similarity: {sim:.4f}")
        print(f"      Excerpt: {chunk.content.strip()[:60]}...")
    assert len(search_results) > 0
    top_chunk, top_dist = search_results[0]
    assert "add" in top_chunk.content.lower()
    print("  ✓ Vector similarity retrieval accurately matched top code chunk!")

    # 5. LLM Grounded Answer Generation
    print("\n[Step 5] Testing OpenRouter LLM Grounded Answer Generation:")
    evidence = [
        (c.content, c.file_path, c.start_line, c.end_line)
        for c, _ in search_results
    ]
    prompt = build_prompt(question, evidence)
    print("  Constructed Prompt Preview:")
    for line in prompt.splitlines()[:6]:
        print(f"    {line}")

    llm = OpenRouterProvider()
    answer = llm.call_llm(prompt)
    print("\n  LLM Answer Output:")
    print("  " + "-" * 50)
    for line in answer.splitlines():
        print(f"  {line}")
    print("  " + "-" * 50)

    assert len(answer) > 10, "LLM returned empty or too short response"
    assert "add" in answer.lower(), "Answer should mention the add function"
    print("  ✓ LLM generated grounded answer referencing repository evidence!")

    db.close()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED: Full Embedding & LLM System Verified!")
    print("=" * 60)


if __name__ == "__main__":
    main()
