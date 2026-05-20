"""Tests for AntiPatternTracker."""

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.lifecycle.anti_pattern import AntiPatternTracker


def _make_anti_pattern_node(node_id: str, tool_tags: list[str]) -> MemoryNode:
    return MemoryNode(
        id=node_id,
        name=f"anti-{node_id}",
        content="Don't use this tool",
        tags=["anti-pattern"] + tool_tags,
    )


class TestAntiPatternTracker:
    def test_record_injection(self):
        tracker = AntiPatternTracker()
        node = _make_anti_pattern_node("ap1", ["git", "push"])
        tracker.record_injection(node)
        assert tracker.active_count == 1

    def test_ignores_non_anti_pattern(self):
        tracker = AntiPatternTracker()
        node = MemoryNode(id="normal", name="n", content="normal memory", tags=["preference"])
        tracker.record_injection(node)
        assert tracker.active_count == 0

    def test_get_contradicted_by_tool_name(self):
        tracker = AntiPatternTracker()
        node = _make_anti_pattern_node("ap1", ["git", "push"])
        tracker.record_injection(node)

        contradicted = tracker.get_contradicted("git")
        assert "ap1" in contradicted

    def test_no_contradiction_for_unrelated_tool(self):
        tracker = AntiPatternTracker()
        node = _make_anti_pattern_node("ap1", ["git", "push"])
        tracker.record_injection(node)

        contradicted = tracker.get_contradicted("npm")
        assert contradicted == []

    def test_case_insensitive_tool_match(self):
        tracker = AntiPatternTracker()
        node = _make_anti_pattern_node("ap1", ["Git", "Push"])
        tracker.record_injection(node)

        contradicted = tracker.get_contradicted("GIT")
        assert "ap1" in contradicted

    def test_clear_turn_resets(self):
        tracker = AntiPatternTracker()
        node = _make_anti_pattern_node("ap1", ["git"])
        tracker.record_injection(node)
        assert tracker.active_count == 1

        tracker.clear_turn()
        assert tracker.active_count == 0
        assert tracker.get_contradicted("git") == []

    def test_multiple_anti_patterns(self):
        tracker = AntiPatternTracker()
        tracker.record_injection(_make_anti_pattern_node("ap1", ["git"]))
        tracker.record_injection(_make_anti_pattern_node("ap2", ["git", "rm"]))
        tracker.record_injection(_make_anti_pattern_node("ap3", ["npm"]))

        git_contradicted = tracker.get_contradicted("git")
        assert set(git_contradicted) == {"ap1", "ap2"}

        rm_contradicted = tracker.get_contradicted("rm")
        assert rm_contradicted == ["ap2"]
