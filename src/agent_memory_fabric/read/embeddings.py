"""Embedding generation interface for vector similarity scoring.

Supports pre-computed vectors for testing (no model dependency)
and optional sentence-transformers integration for production.
"""

from __future__ import annotations

import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Interface for generating embeddings."""

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimension(self) -> int: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class PrecomputedEmbeddings(EmbeddingProvider):
    """Testing provider that stores pre-computed vectors by content hash."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension
        self._cache: dict[str, list[float]] = {}

    @property
    def dimension(self) -> int:
        return self._dimension

    def register(self, text: str, embedding: list[float]) -> None:
        self._cache[text] = embedding

    def embed(self, text: str) -> list[float]:
        if text in self._cache:
            return self._cache[text]
        return [0.0] * self._dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SentenceTransformerProvider(EmbeddingProvider):
    """Production provider using sentence-transformers (lazy-loaded)."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._dimension_cache: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension_cache is None:
            self._ensure_model()
            self._dimension_cache = self._model.get_sentence_embedding_dimension()
        return self._dimension_cache

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers required. Install with: pip install agent-memory-fabric[full]"
                )

    def embed(self, text: str) -> list[float]:
        self._ensure_model()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        return self._model.encode(texts, normalize_embeddings=True).tolist()
