"""Tests for embedding interface and cosine similarity."""

import pytest

from agent_memory_fabric.read.embeddings import (
    PrecomputedEmbeddings,
    cosine_similarity,
)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_similar_vectors(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        sim = cosine_similarity(a, b)
        assert 0.5 < sim < 1.0

    def test_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_empty_vectors(self):
        assert cosine_similarity([], []) == 0.0

    def test_different_lengths(self):
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


class TestPrecomputedEmbeddings:
    def test_register_and_embed(self):
        provider = PrecomputedEmbeddings(dimension=3)
        provider.register("hello", [1.0, 0.0, 0.0])
        assert provider.embed("hello") == [1.0, 0.0, 0.0]

    def test_unknown_text_returns_zeros(self):
        provider = PrecomputedEmbeddings(dimension=3)
        result = provider.embed("unknown")
        assert result == [0.0, 0.0, 0.0]

    def test_dimension_property(self):
        provider = PrecomputedEmbeddings(dimension=768)
        assert provider.dimension == 768

    def test_embed_batch(self):
        provider = PrecomputedEmbeddings(dimension=2)
        provider.register("a", [1.0, 0.0])
        provider.register("b", [0.0, 1.0])
        results = provider.embed_batch(["a", "b", "c"])
        assert results[0] == [1.0, 0.0]
        assert results[1] == [0.0, 1.0]
        assert results[2] == [0.0, 0.0]
