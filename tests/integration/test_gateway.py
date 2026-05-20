"""Integration tests for the proactive retrieval gateway."""

import pytest

from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.read.embeddings import PrecomputedEmbeddings


@pytest.fixture
def engine(tmp_path):
    return MemoryEngine(vault_path=tmp_path / "vault")


@pytest.fixture
def populated_engine(engine):
    engine.write("User prefers dark mode for all editors", name="dark-mode-pref", tags=["preference"])
    engine.write("AMF uses a lifecycle state machine with four states", name="amf-lifecycle", project="amf")
    engine.write("Meeting with Brennan scheduled for next Tuesday", name="brennan-meeting", tags=["temporal"])
    engine.write("Python is the primary language for the backend", name="python-lang", tags=["tech"])
    engine.write("The proactive retrieval gateway runs on every user message", name="gateway-design", project="amf")
    return engine


class TestRetrieveProactive:
    def test_abstains_on_greeting(self, populated_engine):
        results = populated_engine.retrieve_proactive("hello there friend")
        assert results == []

    def test_abstains_on_short_message(self, populated_engine):
        results = populated_engine.retrieve_proactive("ok")
        assert results == []

    def test_retrieves_relevant_memories(self, populated_engine):
        results = populated_engine.retrieve_proactive("Tell me about the dark mode preference")
        assert len(results) > 0
        names = [r.node.name for r in results]
        assert "dark-mode-pref" in names

    def test_scoped_retrieval(self, populated_engine):
        results = populated_engine.retrieve_proactive(
            "What's the lifecycle design?", scope="amf"
        )
        for r in results:
            assert r.node.project == "amf" or r.node.project is None

    def test_returns_scored_memories(self, populated_engine):
        results = populated_engine.retrieve_proactive("lifecycle state machine design")
        assert len(results) > 0
        assert results[0].total_score >= results[-1].total_score
        assert results[0].tier in ("hot", "warm", "cold")

    def test_respects_top_k(self, populated_engine):
        results = populated_engine.retrieve_proactive("AMF design decisions", top_k=2)
        assert len(results) <= 2

    def test_with_embedding_provider(self, populated_engine):
        provider = PrecomputedEmbeddings(dimension=3)
        provider.register("dark mode preference", [1.0, 0.0, 0.0])
        results = populated_engine.retrieve_proactive(
            "dark mode preference",
            embedding_provider=provider,
        )
        # Should retrieve results via FTS even without sqlite-vec
        assert isinstance(results, list)


class TestUpdateConfidence:
    def test_update_confidence_success(self, populated_engine):
        node = populated_engine.write("Test memory", name="conf-test")
        result = populated_engine.update_confidence(node.id, success=True)
        assert result is not None

    def test_update_confidence_failure(self, populated_engine):
        node = populated_engine.write("Unreliable memory", name="unreliable")
        result = populated_engine.update_confidence(node.id, success=False)
        assert result is not None

    def test_update_nonexistent_returns_none(self, populated_engine):
        result = populated_engine.update_confidence("fake-id", success=True)
        assert result is None
