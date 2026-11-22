"""
Tests for app/services/embedding_provider.py

Validates:
- EmbeddingProvider interface contract (dimension, single embed, batch embed).
- LocalEmbeddingProvider returns 384-dimensional float vectors (all-MiniLM-L6-v2).
- OpenAIEmbeddingProvider returns 1536-dimensional float vectors (text-embedding-3-small).
- VoyageAIEmbeddingProvider returns 1024-dimensional float vectors (voyage-code-3).
- Batch embedding preserves order and count, and forwards batch_size.
- Empty batches return [] without loading or calling endpoints.
- The model is loaded only once across calls and across provider instances (Local).
- Error handling: model-load failures, dimension mismatch, encode failures,
  auth errors, and missing packages raise typed EmbeddingError subclasses.
- Provider factory (create_embedding_provider) cleanly swaps between providers.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.services import embedding_provider as ep
from app.services.embedding_provider import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    EmbeddingAuthenticationError,
    EmbeddingError,
    EmbeddingModelLoadError,
    EmbeddingProvider,
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    OpenRouterEmbeddingProvider,
    VoyageAIEmbeddingProvider,
    create_embedding_provider,
)


class _FakeModel:
    """Stand-in for sentence_transformers.SentenceTransformer used in unit tests."""

    def __init__(
        self,
        dimension: int = 384,
        encode_side_effect: Exception | None = None,
    ) -> None:
        self._dimension = dimension
        self._encode_side_effect = encode_side_effect
        self.encode_calls = 0
        self.last_batch_size = None
        self.last_texts = None

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts,
        batch_size: int = 32,
        convert_to_numpy: bool = True,
        show_progress_bar: bool = False,
        normalize_embeddings: bool = False,
    ):
        self.encode_calls += 1
        self.last_batch_size = batch_size
        self.last_texts = list(texts)
        if self._encode_side_effect is not None:
            raise self._encode_side_effect
        return [
            [float((len(t) + i) % 1000) / 1000.0 for i in range(self._dimension)]
            for t in texts
        ]


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
    """Ensure each test starts and ends with a clean module-level model cache."""
    ep._reset_cached_model()
    ep._default_provider = None
    yield
    ep._reset_cached_model()
    ep._default_provider = None


# ===========================================================================
# 1. Interface and Local Provider
# ===========================================================================


def test_embedding_dimension_constant_and_property():
    assert EMBEDDING_DIMENSION == 384
    provider = LocalEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 384
    assert provider.model_name == DEFAULT_EMBEDDING_MODEL == "all-MiniLM-L6-v2"


def test_invalid_batch_size_rejected():
    with pytest.raises(ValueError):
        LocalEmbeddingProvider(batch_size=0)
    with pytest.raises(ValueError):
        OpenAIEmbeddingProvider(batch_size=-1)
    with pytest.raises(ValueError):
        VoyageAIEmbeddingProvider(batch_size=0)
    with pytest.raises(ValueError):
        OpenRouterEmbeddingProvider(batch_size=0)


def test_embed_single_returns_384_floats():
    fake = _FakeModel(dimension=384)
    with patch.object(ep, "_load_sentence_transformer", return_value=fake):
        provider = LocalEmbeddingProvider()
        vec = provider.embed("def add(a, b): return a + b")
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)


def test_embed_batch_preserves_order_and_count():
    fake = _FakeModel(dimension=384)
    texts = ["alpha", "beta function", "gamma class"]
    with patch.object(ep, "_load_sentence_transformer", return_value=fake):
        provider = LocalEmbeddingProvider()
        vectors = provider.embed_batch(texts)
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)
    assert vectors[0] != vectors[1]
    assert vectors[1] != vectors[2]
    assert vectors[0] != vectors[2]


def test_embed_batch_empty_returns_empty_without_loading():
    with patch.object(ep, "_load_sentence_transformer") as mock_loader:
        provider = LocalEmbeddingProvider()
        result = provider.embed_batch([])
    assert result == []
    mock_loader.assert_not_called()


def test_embed_batch_none_raises_value_error():
    provider = LocalEmbeddingProvider()
    with pytest.raises(ValueError):
        provider.embed_batch(None)


def test_batch_size_forwarded_to_model():
    fake = _FakeModel(dimension=384)
    with patch.object(ep, "_load_sentence_transformer", return_value=fake):
        provider = LocalEmbeddingProvider(batch_size=8)
        provider.embed_batch(["one", "two"])
    assert fake.last_batch_size == 8


def test_model_loaded_once_across_multiple_calls():
    fake = _FakeModel(dimension=384)
    with patch.object(ep, "_load_sentence_transformer", return_value=fake) as mock_loader:
        provider = LocalEmbeddingProvider()
        provider.embed("a")
        provider.embed("b")
        provider.embed_batch(["c", "d"])
    assert mock_loader.call_count == 1
    assert fake.encode_calls == 3


def test_model_shared_across_provider_instances():
    fake = _FakeModel(dimension=384)
    with patch.object(ep, "_load_sentence_transformer", return_value=fake) as mock_loader:
        p1 = LocalEmbeddingProvider()
        p2 = LocalEmbeddingProvider()
        p1.embed("x")
        p2.embed_batch(["y", "z"])
    assert mock_loader.call_count == 1


def test_get_embedding_provider_returns_shared_instance():
    a = ep.get_embedding_provider()
    b = ep.get_embedding_provider()
    assert a is b
    assert isinstance(a, EmbeddingProvider)


# ===========================================================================
# 2. Error handling (Local)
# ===========================================================================


def test_dimension_mismatch_raises_model_load_error():
    fake = _FakeModel(dimension=768)
    with patch.object(ep, "_load_sentence_transformer", return_value=fake):
        provider = LocalEmbeddingProvider()
        with pytest.raises(EmbeddingModelLoadError):
            provider.embed("anything")


def test_model_load_failure_propagates_model_load_error():
    def boom(model_name: str):
        raise EmbeddingModelLoadError("model unavailable")

    with patch.object(ep, "_load_sentence_transformer", side_effect=boom):
        provider = LocalEmbeddingProvider()
        with pytest.raises(EmbeddingModelLoadError):
            provider.embed_batch(["x"])


def test_encode_failure_wrapped_as_embedding_error():
    fake = _FakeModel(dimension=384, encode_side_effect=RuntimeError("gpu oom"))
    with patch.object(ep, "_load_sentence_transformer", return_value=fake):
        provider = LocalEmbeddingProvider()
        with pytest.raises(EmbeddingError) as excinfo:
            provider.embed_batch(["x"])
    assert isinstance(excinfo.value, EmbeddingError)
    assert not isinstance(excinfo.value, RuntimeError)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "gpu oom" in str(excinfo.value.__cause__)
    assert "Embedding generation failed" in str(excinfo.value)


def test_missing_package_raises_model_load_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    provider = LocalEmbeddingProvider()
    with pytest.raises(EmbeddingModelLoadError):
        provider.embed("x")


# ===========================================================================
# 3. OpenAI Embedding Provider
# ===========================================================================


def test_openai_provider_interface_and_dimensions():
    provider = OpenAIEmbeddingProvider(model_name="text-embedding-3-small", api_key="sk-test")
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 1536

    large_provider = OpenAIEmbeddingProvider(model_name="text-embedding-3-large", api_key="sk-test")
    assert large_provider.dimension == 3072


def test_openai_missing_api_key_raises_auth_error():
    provider = OpenAIEmbeddingProvider(api_key=None)
    with patch.object(ep.settings, "openai_api_key", None):
        provider.api_key = None
        with pytest.raises(EmbeddingAuthenticationError):
            provider.embed("hello world")


def test_openai_embed_batch_success_with_mock_client():
    mock_client = MagicMock()
    mock_item1 = MagicMock(index=0, embedding=[0.1] * 1536)
    mock_item2 = MagicMock(index=1, embedding=[0.2] * 1536)
    mock_client.embeddings.create.return_value = MagicMock(data=[mock_item1, mock_item2])

    provider = OpenAIEmbeddingProvider(api_key="sk-test", client=mock_client)
    res = provider.embed_batch(["function one", "function two"])

    assert len(res) == 2
    assert len(res[0]) == 1536
    assert len(res[1]) == 1536
    assert res[0][0] == 0.1
    assert res[1][0] == 0.2


def test_openai_embed_empty_batch():
    provider = OpenAIEmbeddingProvider(api_key="sk-test")
    assert provider.embed_batch([]) == []


# ===========================================================================
# 4. Voyage AI Embedding Provider
# ===========================================================================


def test_voyage_provider_interface_and_dimensions():
    provider = VoyageAIEmbeddingProvider(model_name="voyage-code-3", api_key="pa-test")
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 1024

    lite_provider = VoyageAIEmbeddingProvider(model_name="voyage-3-lite", api_key="pa-test")
    assert lite_provider.dimension == 512


def test_voyage_missing_api_key_raises_auth_error():
    provider = VoyageAIEmbeddingProvider(api_key=None)
    with patch.object(ep.settings, "voyage_api_key", None):
        provider.api_key = None
        with pytest.raises(EmbeddingAuthenticationError):
            provider.embed("hello world")


def test_voyage_embed_batch_success_with_mock_client():
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(
        embeddings=[[0.05] * 1024, [0.08] * 1024]
    )

    provider = VoyageAIEmbeddingProvider(api_key="pa-test", client=mock_client)
    res = provider.embed_batch(["def search(): pass", "class Index: pass"])

    assert len(res) == 2
    assert len(res[0]) == 1024
    assert len(res[1]) == 1024
    assert res[0][0] == 0.05


def test_voyage_embed_empty_batch():
    provider = VoyageAIEmbeddingProvider(api_key="pa-test")
    assert provider.embed_batch([]) == []


# ===========================================================================
# 5. OpenRouter Embedding Provider
# ===========================================================================


def test_openrouter_provider_interface_and_dimensions():
    provider = OpenRouterEmbeddingProvider(
        model_name="nvidia/nemotron-3-embed-1b:free", api_key="sk-test"
    )
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 2048

    custom_provider = OpenRouterEmbeddingProvider(
        model_name="custom-model", dimension=1024, api_key="sk-test"
    )
    assert custom_provider.dimension == 1024


def test_openrouter_missing_api_key_raises_auth_error():
    provider = OpenRouterEmbeddingProvider(api_key=None)
    with patch.object(ep.settings, "openrouter_api_key", None):
        provider.api_key = None
        with pytest.raises(EmbeddingAuthenticationError):
            provider.embed("hello world")


def test_openrouter_embed_batch_success_with_mock_client():
    mock_client = MagicMock()
    mock_item1 = MagicMock(index=0, embedding=[0.05] * 2048)
    mock_item2 = MagicMock(index=1, embedding=[0.12] * 2048)
    mock_client.embeddings.create.return_value = MagicMock(data=[mock_item1, mock_item2])

    provider = OpenRouterEmbeddingProvider(api_key="sk-test", client=mock_client)
    res = provider.embed_batch(["def search(): pass", "class Index: pass"])

    assert len(res) == 2
    assert len(res[0]) == 2048
    assert len(res[1]) == 2048
    assert res[0][0] == 0.05
    assert res[1][0] == 0.12


def test_openrouter_embed_empty_batch():
    provider = OpenRouterEmbeddingProvider(api_key="sk-test")
    assert provider.embed_batch([]) == []


# ===========================================================================
# 6. Provider Factory and Model Swapping
# ===========================================================================


def test_create_embedding_provider_swapping():
    # Local provider
    local_p = create_embedding_provider(provider_type="local")
    assert isinstance(local_p, LocalEmbeddingProvider)
    assert local_p.dimension == 384

    # OpenAI provider
    openai_p = create_embedding_provider(provider_type="openai", api_key="test-key")
    assert isinstance(openai_p, OpenAIEmbeddingProvider)
    assert openai_p.dimension == 1536

    # Voyage AI provider
    voyage_p = create_embedding_provider(provider_type="voyage", api_key="test-key")
    assert isinstance(voyage_p, VoyageAIEmbeddingProvider)
    assert voyage_p.dimension == 1024

    # OpenRouter provider
    openrouter_p = create_embedding_provider(
        provider_type="openrouter",
        model_name="nvidia/nemotron-3-embed-1b:free",
        api_key="sk-test",
    )
    assert isinstance(openrouter_p, OpenRouterEmbeddingProvider)
    assert openrouter_p.dimension == 2048


def test_create_embedding_provider_unknown_raises():
    with pytest.raises(ValueError) as exc:
        create_embedding_provider(provider_type="unknown-provider")
    assert "Unknown embedding provider" in str(exc.value)


# ===========================================================================
# 6. Real local model integration (skipped when sentence-transformers is unavailable)
# ===========================================================================


def test_real_model_embedding(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    pytest.importorskip("sentence_transformers")

    ep._reset_cached_model()
    provider = LocalEmbeddingProvider()

    vec = provider.embed("def hello(): print('hi')")
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)

    batch = provider.embed_batch(["def a(): pass", "class B: pass"])
    assert len(batch) == 2
    assert all(len(v) == 384 for v in batch)
    assert ep._cached_model is not None
