"""Tests for LLM integration — provider, contradiction detection."""

import pytest

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.llm.contradiction import detect_contradictions
from agent_memory_fabric.llm.provider import MockProvider


class TestMockProvider:
    def test_default_response(self):
        mock = MockProvider(default_response="NO")
        assert mock.complete("sys", "user") == "NO"

    def test_queued_responses(self):
        mock = MockProvider()
        mock.set_responses(["first", "second", "third"])
        assert mock.complete("s", "u") == "first"
        assert mock.complete("s", "u") == "second"
        assert mock.complete("s", "u") == "third"

    def test_keyword_response(self):
        mock = MockProvider()
        mock.set_response_for("shanghai", "YES: location changed")
        assert mock.complete("sys", "I moved from Shanghai") == "YES: location changed"
        assert mock.complete("sys", "I like Python") == "NO"

    def test_call_log(self):
        mock = MockProvider()
        mock.complete("system prompt", "user prompt")
        assert len(mock.call_log) == 1
        assert mock.call_log[0] == ("system prompt", "user prompt")


class TestContradictionDetection:
    def test_detects_location_change(self):
        mock = MockProvider(default_response="NO")
        mock.set_response_for("lives in shanghai", "YES: user moved to a new city")

        existing = [
            MemoryNode(name="location", content="User lives in Shanghai"),
            MemoryNode(name="language", content="User prefers Python"),
        ]

        results = detect_contradictions(
            "I moved to Suzhou last week",
            existing,
            mock,
        )

        assert len(results) == 1
        assert results[0][0].name == "location"
        assert "city" in results[0][1].lower()

    def test_no_contradiction(self):
        mock = MockProvider(default_response="NO")

        existing = [
            MemoryNode(name="lang", content="User prefers Python"),
        ]

        results = detect_contradictions("I also started learning Rust", existing, mock)
        assert results == []

    def test_respects_max_comparisons(self):
        mock = MockProvider(default_response="NO")
        existing = [MemoryNode(name=f"n{i}", content=f"fact {i}") for i in range(50)]

        detect_contradictions("new info", existing, mock, max_comparisons=5)
        assert len(mock.call_log) == 5

    def test_handles_multiple_contradictions(self):
        mock = MockProvider(default_response="YES: superseded")

        existing = [
            MemoryNode(name="a", content="studying for AWS"),
            MemoryNode(name="b", content="lives in Shanghai"),
            MemoryNode(name="c", content="single"),
        ]

        results = detect_contradictions("passed AWS, moved to Suzhou, got married", existing, mock)
        assert len(results) == 3

    def test_empty_existing_nodes(self):
        mock = MockProvider()
        results = detect_contradictions("new info", [], mock)
        assert results == []
        assert len(mock.call_log) == 0


class TestEngineContradictionIntegration:
    def test_detect_and_archive(self, tmp_path):
        from agent_memory_fabric.core.engine import MemoryEngine

        engine = MemoryEngine(vault_path=tmp_path / "vault")
        engine.write("User lives in Shanghai", name="location")
        engine.write("User prefers Python", name="language")

        mock = MockProvider()
        mock.set_response_for("shanghai", "YES: location changed")

        result = engine.detect_and_archive_contradictions(
            "I moved to Suzhou last week", mock
        )

        assert len(result["direct"]) == 1
        node_id = result["direct"][0][0]
        node = engine.read(node_id)
        assert node.state == LifecycleState.ARCHIVED

    def test_no_contradictions_leaves_nodes_active(self, tmp_path):
        from agent_memory_fabric.core.engine import MemoryEngine

        engine = MemoryEngine(vault_path=tmp_path / "vault")
        engine.write("User prefers dark mode", name="pref")

        mock = MockProvider(default_response="NO")
        result = engine.detect_and_archive_contradictions("I also like vim", mock)
        assert result["direct"] == []

        node_data = engine.list_nodes()
        assert all(n["state"] == "active" for n in node_data)
