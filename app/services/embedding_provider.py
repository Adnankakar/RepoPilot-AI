"""
embedding_provider.py

Text embedding providers for RepoPilot AI.

This module defines the reusable EmbeddingProvider interface together with
concrete implementations:
1. LocalEmbeddingProvider: backed by local sentence-transformers (all-MiniLM-L6-v2
   by default, 384 dimensions, zero external API dependencies).
2. OpenAIEmbeddingProvider: backed by OpenAI embeddings API (text-embedding-3-small,
   text-embedding-3-large, text-embedding-ada-002).
3. VoyageAIEmbeddingProvider: backed by Voyage AI code embeddings API
   (voyage-code-3, voyage-3, voyage-3-lite).

Key Features:
- Reusable interface: EmbeddingProvider declares the contract (``dimension``,
  single ``embed``, and ``embed_batch``) so models can be swapped and compared
  without altering downstream chunking or indexing code.
- Provider factory: ``create_embedding_provider()`` and ``get_embedding_provider()``
  allow seamless swapping via configuration or explicit parameters.
- Model caching: local models are loaded lazily and cached at the module level
  behind a lock to avoid redundant memory allocation.
- Typed error handling: import, authentication, and encoding failures are
  translated into typed EmbeddingError subclasses with clear error messages.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Sequence

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# all-MiniLM-L6-v2 produces 384-dimensional dense sentence embeddings.
EMBEDDING_DIMENSION: int = 384

# The default sentence-transformers model used for local embeddings.
DEFAULT_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# Default batch size passed to models / API endpoints.
DEFAULT_BATCH_SIZE: int = 32

# Known dimensions for common OpenAI and Voyage AI models
OPENAI_MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

VOYAGE_MODEL_DIMENSIONS: dict[str, int] = {
    "voyage-code-3": 1024,
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-code-2": 1536,
    "voyage-2": 1024,
}

OPENROUTER_MODEL_DIMENSIONS: dict[str, int] = {
    "nvidia/nemotron-3-embed-1b:free": 2048,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EmbeddingError(Exception):
    """Base error for any failure while generating text embeddings."""


class EmbeddingModelLoadError(EmbeddingError):
    """Raised when the embedding model cannot be imported or loaded."""


class EmbeddingAuthenticationError(EmbeddingError):
    """Raised when an API key is missing or rejected by a remote provider."""


# ---------------------------------------------------------------------------
# Reusable interface
# ---------------------------------------------------------------------------


class EmbeddingProvider(ABC):
    """
    Abstract interface for text embedding providers.

    A provider converts text (or batches of text) into fixed-dimensional float
    vectors. Implementations may be local (in-process models) or remote
    (hosted APIs) without changing calling code.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The dimensionality of every vector produced by this provider."""

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Embed a batch of texts.

        Returns one vector per input text, in the same order. An empty input
        returns an empty list without loading the model.
        """

    def embed(self, text: str) -> list[float]:
        """Embed a single text into a vector."""
        return self.embed_batch([text])[0]


# ---------------------------------------------------------------------------
# Module-level model cache (load once, share across all local instances)
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_cached_model = None
_cached_model_name: str | None = None


def _reset_cached_model() -> None:
    """Clear the cached embedding model. Intended for tests."""
    global _cached_model, _cached_model_name
    with _model_lock:
        _cached_model = None
        _cached_model_name = None


def _load_sentence_transformer(model_name: str):
    """
    Instantiate a SentenceTransformer for *model_name*.

    Isolated as a module-level function so tests can patch this seam without
    requiring the real sentence-transformers package to be installed.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingModelLoadError(
            "sentence-transformers is required for local embeddings but is "
            "not installed."
        ) from exc
    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise EmbeddingModelLoadError(
            f"Failed to load embedding model '{model_name}': {exc}"
        ) from exc


def _model_dimension(model) -> int:
    """Return the embedding dimension reported by a loaded model."""
    try:
        # get_embedding_dimension() is the current API (sentence-transformers ≥ 3.x).
        # get_sentence_embedding_dimension() still works but emits a FutureWarning.
        if hasattr(model, "get_embedding_dimension"):
            return int(model.get_embedding_dimension())
        return int(model.get_sentence_embedding_dimension())
    except Exception as exc:
        raise EmbeddingModelLoadError(
            f"Could not determine embedding dimension: {exc}"
        ) from exc


def _to_float_matrix(embeddings) -> list[list[float]]:
    """Convert a numpy array or nested list of numbers to list[list[float]]."""
    rows = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
    return [[float(x) for x in row] for row in rows]


# ---------------------------------------------------------------------------
# 1. Local sentence-transformers implementation
# ---------------------------------------------------------------------------


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by a local sentence-transformers model.

    The model is loaded lazily on first use and cached at the module level so
    that every LocalEmbeddingProvider instance in the process shares one loaded
    model. Defaults to all-MiniLM-L6-v2 (384 dims).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        expected_dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer.")
        self.model_name = model_name
        self.batch_size = batch_size
        self._expected_dimension = expected_dimension

    @property
    def dimension(self) -> int:
        return self._expected_dimension

    def _get_model(self):
        """Return the cached model, loading it once if needed (thread-safe)."""
        global _cached_model, _cached_model_name

        if _cached_model is not None and _cached_model_name == self.model_name:
            return _cached_model

        with _model_lock:
            # Double-checked locking after acquiring the lock.
            if _cached_model is not None and _cached_model_name == self.model_name:
                return _cached_model

            model = _load_sentence_transformer(self.model_name)

            actual_dim = _model_dimension(model)
            if actual_dim != self._expected_dimension:
                raise EmbeddingModelLoadError(
                    f"Model '{self.model_name}' produces {actual_dim}-dimensional "
                    f"vectors; expected {self._expected_dimension}."
                )

            _cached_model = model
            _cached_model_name = self.model_name
            logger.info(
                "Loaded embedding model '%s' (dimension=%d).",
                self.model_name,
                self._expected_dimension,
            )
            return _cached_model

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if texts is None:
            raise ValueError("texts must not be None.")

        texts_list = list(texts)
        if not texts_list:
            return []

        try:
            model = self._get_model()
            embeddings = model.encode(
                texts_list,
                batch_size=self.batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=False,
            )
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(
                f"Embedding generation failed for {len(texts_list)} text(s): {exc}"
            ) from exc

        return _to_float_matrix(embeddings)


# ---------------------------------------------------------------------------
# 2. OpenAI Embedding Provider
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by OpenAI's Embeddings API.

    Supported models include:
    - text-embedding-3-small (default, 1536 dims)
    - text-embedding-3-large (3072 dims)
    - text-embedding-ada-002 (1536 dims)
    """

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: str | None = None,
        dimension: int | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        client: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer.")
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key
        self.batch_size = batch_size
        self._client = client

        # Determine dimensionality
        if dimension is not None:
            self._dimension = dimension
        else:
            self._dimension = OPENAI_MODEL_DIMENSIONS.get(model_name, 1536)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if texts is None:
            raise ValueError("texts must not be None.")

        texts_list = list(texts)
        if not texts_list:
            return []

        if not self.api_key and self._client is None:
            raise EmbeddingAuthenticationError(
                "OpenAI API key is missing. Set OPENAI_API_KEY in the environment or .env."
            )

        vectors: list[list[float]] = []

        # Process in chunks of batch_size
        for i in range(0, len(texts_list), self.batch_size):
            chunk = texts_list[i : i + self.batch_size]
            vectors.extend(self._call_api(chunk))

        return vectors

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        # If a mock client was injected, call it directly
        if self._client is not None:
            try:
                response = self._client.embeddings.create(
                    model=self.model_name,
                    input=texts,
                )
                sorted_data = sorted(response.data, key=lambda item: item.index)
                return [list(item.embedding) for item in sorted_data]
            except Exception as exc:
                raise EmbeddingError(f"OpenAI embedding call failed: {exc}") from exc

        # Use HTTPX directly to avoid requiring openai package to be installed
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json=payload,
                )
                if res.status_code in (401, 403):
                    raise EmbeddingAuthenticationError(
                        f"OpenAI authentication failed ({res.status_code}): {res.text}"
                    )
                if res.status_code != 200:
                    raise EmbeddingError(
                        f"OpenAI API returned status {res.status_code}: {res.text}"
                    )

                data = res.json().get("data", [])
                sorted_data = sorted(data, key=lambda item: item["index"])
                return [[float(x) for x in item["embedding"]] for item in sorted_data]
        except (EmbeddingAuthenticationError, EmbeddingError):
            raise
        except Exception as exc:
            raise EmbeddingError(f"OpenAI embedding request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 3. Voyage AI Embedding Provider
# ---------------------------------------------------------------------------


class VoyageAIEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by Voyage AI's Embeddings API.

    Specialized in code and documentation retrieval:
    - voyage-code-3 (default, 1024 dims)
    - voyage-3 (1024 dims)
    - voyage-3-lite (512 dims)
    """

    def __init__(
        self,
        model_name: str = "voyage-code-3",
        api_key: str | None = None,
        dimension: int | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        client: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer.")
        self.model_name = model_name
        self.api_key = api_key or settings.voyage_api_key
        self.batch_size = batch_size
        self._client = client

        # Determine dimensionality
        if dimension is not None:
            self._dimension = dimension
        else:
            self._dimension = VOYAGE_MODEL_DIMENSIONS.get(model_name, 1024)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if texts is None:
            raise ValueError("texts must not be None.")

        texts_list = list(texts)
        if not texts_list:
            return []

        if not self.api_key and self._client is None:
            raise EmbeddingAuthenticationError(
                "Voyage AI API key is missing. Set VOYAGE_API_KEY in the environment or .env."
            )

        vectors: list[list[float]] = []

        for i in range(0, len(texts_list), self.batch_size):
            chunk = texts_list[i : i + self.batch_size]
            vectors.extend(self._call_api(chunk))

        return vectors

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        # If a mock client was injected, call it directly
        if self._client is not None:
            try:
                response = self._client.embed(
                    texts=texts,
                    model=self.model_name,
                )
                return [list(vec) for vec in response.embeddings]
            except Exception as exc:
                raise EmbeddingError(f"Voyage AI embedding call failed: {exc}") from exc

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
            "input_type": "document",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers=headers,
                    json=payload,
                )
                if res.status_code in (401, 403):
                    raise EmbeddingAuthenticationError(
                        f"Voyage AI authentication failed ({res.status_code}): {res.text}"
                    )
                if res.status_code != 200:
                    raise EmbeddingError(
                        f"Voyage AI API returned status {res.status_code}: {res.text}"
                    )

                data = res.json().get("data", [])
                return [[float(x) for x in item["embedding"]] for item in data]
        except (EmbeddingAuthenticationError, EmbeddingError):
            raise
        except Exception as exc:
            raise EmbeddingError(f"Voyage AI embedding request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 4. OpenRouter Embedding Provider
# ---------------------------------------------------------------------------


class OpenRouterEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by OpenRouter's Embeddings API.

    Supported models include:
    - nvidia/nemotron-3-embed-1b:free (default, 2048 dims)
    """

    _endpoint = "https://openrouter.ai/api/v1/embeddings"

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        dimension: int | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        client: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer.")
        self.model_name = model_name or settings.embedding_model or "nvidia/nemotron-3-embed-1b:free"
        self.api_key = api_key or settings.openrouter_api_key
        self.batch_size = batch_size
        self._client = client

        # Determine dimensionality
        if dimension is not None:
            self._dimension = dimension
        else:
            self._dimension = OPENROUTER_MODEL_DIMENSIONS.get(self.model_name, 2048)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if texts is None:
            raise ValueError("texts must not be None.")

        texts_list = list(texts)
        if not texts_list:
            return []

        if not self.api_key and self._client is None:
            raise EmbeddingAuthenticationError(
                "OpenRouter API key is missing. Set OPENROUTER_API_KEY in the environment or .env."
            )

        vectors: list[list[float]] = []

        # Process in chunks of batch_size
        for i in range(0, len(texts_list), self.batch_size):
            chunk = texts_list[i : i + self.batch_size]
            vectors.extend(self._call_api(chunk))

        return vectors

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        # If a mock client was injected, call it directly
        if self._client is not None:
            try:
                if hasattr(self._client, "embeddings"):
                    response = self._client.embeddings.create(
                        model=self.model_name,
                        input=texts,
                        encoding_format="float",
                    )
                    data = getattr(response, "data", [])
                    sorted_data = sorted(
                        data,
                        key=lambda item: (
                            item.get("index", 0)
                            if isinstance(item, dict)
                            else getattr(item, "index", 0)
                        ),
                    )
                    return [
                        [
                            float(x)
                            for x in (
                                item["embedding"]
                                if isinstance(item, dict)
                                else getattr(item, "embedding")
                            )
                        ]
                        for item in sorted_data
                    ]
                elif hasattr(self._client, "embed"):
                    response = self._client.embed(
                        texts=texts,
                        model=self.model_name,
                    )
                    return [list(vec) for vec in response.embeddings]
            except Exception as exc:
                raise EmbeddingError(f"OpenRouter embedding call failed: {exc}") from exc

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
            "encoding_format": "float",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                )
                if res.status_code in (401, 403):
                    raise EmbeddingAuthenticationError(
                        f"OpenRouter authentication failed ({res.status_code}): {res.text}"
                    )
                if res.status_code != 200:
                    raise EmbeddingError(
                        f"OpenRouter API returned status {res.status_code}: {res.text}"
                    )

                data = res.json().get("data", [])
                sorted_data = sorted(
                    data,
                    key=lambda item: (
                        item.get("index", 0)
                        if isinstance(item, dict)
                        else getattr(item, "index", 0)
                    ),
                )
                return [
                    [
                        float(x)
                        for x in (
                            item["embedding"]
                            if isinstance(item, dict)
                            else getattr(item, "embedding")
                        )
                    ]
                    for item in sorted_data
                ]
        except (EmbeddingAuthenticationError, EmbeddingError):
            raise
        except Exception as exc:
            raise EmbeddingError(f"OpenRouter embedding request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory and Shared Provider Accessors
# ---------------------------------------------------------------------------

_default_provider: EmbeddingProvider | None = None


def create_embedding_provider(
    provider_type: str | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    **kwargs: Any,
) -> EmbeddingProvider:
    """
    Factory function to instantiate an EmbeddingProvider based on type.

    Parameters:
        provider_type: "local", "openai", or "voyage" (case-insensitive).
                       Defaults to settings.embedding_provider.
        model_name: Optional model override. Defaults to provider-specific default.
        api_key: Optional API key override for remote providers.
        batch_size: Batch size for chunk embedding.
    """
    provider_type = (provider_type or settings.embedding_provider or "local").lower().strip()

    if provider_type in ("local", "sentence-transformers", "sentence_transformers"):
        return LocalEmbeddingProvider(
            model_name=model_name or settings.embedding_model or DEFAULT_EMBEDDING_MODEL,
            batch_size=batch_size,
            **kwargs,
        )
    elif provider_type == "openai":
        return OpenAIEmbeddingProvider(
            model_name=model_name or "text-embedding-3-small",
            api_key=api_key or settings.openai_api_key,
            batch_size=batch_size,
            **kwargs,
        )
    elif provider_type in ("voyage", "voyageai", "voyage_ai"):
        return VoyageAIEmbeddingProvider(
            model_name=model_name or "voyage-code-3",
            api_key=api_key or settings.voyage_api_key,
            batch_size=batch_size,
            **kwargs,
        )
    elif provider_type == "openrouter":
        return OpenRouterEmbeddingProvider(
            model_name=model_name or settings.embedding_model or "nvidia/nemotron-3-embed-1b:free",
            api_key=api_key or settings.openrouter_api_key,
            batch_size=batch_size,
            **kwargs,
        )
    else:
        raise ValueError(
            f"Unknown embedding provider '{provider_type}'. "
            "Supported providers: 'local', 'openai', 'voyage', 'openrouter'."
        )


def get_embedding_provider() -> EmbeddingProvider:
    """
    Return a process-wide shared EmbeddingProvider instance configured by settings.

    Guarantees the model or connection is initialized once per process.
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = create_embedding_provider()
    return _default_provider
