#!/usr/bin/env python
"""
Quick sanity‑check that the OpenRouter embedding provider is active
and returns a vector of the expected dimension.
"""

from pathlib import Path
import sys

# Add repository root to PYTHONPATH
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from app.services.embedding_provider import get_embedding_provider


def main() -> None:
    provider = get_embedding_provider()

    # Show current dimension (may be unknown until first call)
    try:
        dim = provider.dimension
    except Exception:
        dim = "(unknown – will be set after first embedding)"
    print(f"Embedding provider: {provider.__class__.__name__}")
    print(f"Configured model   : {provider.model_name}")
    print(f"Current dimension  : {dim}")

    # Embed a short sample text
    sample = "Hello RepoPilot AI – this is a test."
    vector = provider.embed(sample)

    print("\n--- Sample embedding ---")
    print(f"Text   : {sample!r}")
    print(f"Length : {len(vector)}")
    print(f"First 5 values: {vector[:5]!r}")

    # Verify dimension matches
    if hasattr(provider, "dimension"):
        try:
            assert provider.dimension == len(vector)
            print("\n✅ Dimension matches the returned vector.")
        except AssertionError:
            print("\n⚠️  Dimension reported does NOT match the vector length!")
            print(f"Reported: {provider.dimension}, actual: {len(vector)}")


if __name__ == "__main__":
    main()
