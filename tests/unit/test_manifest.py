"""Tests for MemoryManifest."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.core.node import MemoryNode, MemoryType
from agent_memory_fabric.read.manifest import MemoryManifest


def _node(name, content="Some content.", modified_days_ago=0, mem_type=MemoryType.PROJECT):
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=f"id-{name}", name=name, content=content,
        type=mem_type, modified=now - timedelta(days=modified_days_ago),
    )


class TestMemoryManifest:
    def test_empty_corpus(self):
        m = MemoryManifest()
        assert m.generate([]) == ""

    def test_format_contains_type_and_name(self):
        m = MemoryManifest()
        nodes = [_node("dark-mode", "User prefers dark mode in editors.", mem_type=MemoryType.FEEDBACK)]
        result = m.generate(nodes)
        assert "[feedback]" in result
        assert "dark-mode" in result

    def test_sorted_newest_first(self):
        m = MemoryManifest()
        old = _node("old-fact", modified_days_ago=30)
        new = _node("new-fact", modified_days_ago=0)
        result = m.generate([old, new])
        lines = result.strip().split("\n")
        assert "new-fact" in lines[0]
        assert "old-fact" in lines[1]

    def test_truncates_at_max_lines(self):
        m = MemoryManifest(max_lines=5)
        nodes = [_node(f"node-{i}", modified_days_ago=i) for i in range(20)]
        result = m.generate(nodes)
        lines = result.strip().split("\n")
        assert len(lines) == 5

    def test_truncates_at_max_bytes(self):
        m = MemoryManifest(max_bytes=200)
        nodes = [_node(f"node-{i}", content="x" * 100, modified_days_ago=i) for i in range(50)]
        result = m.generate(nodes)
        assert len(result.encode("utf-8")) <= 200

    def test_first_sentence_extraction(self):
        m = MemoryManifest()
        nodes = [_node("test", "First sentence here. Second sentence not shown.")]
        result = m.generate(nodes)
        assert "First sentence here." in result
        assert "Second" not in result

    def test_long_content_truncated(self):
        m = MemoryManifest()
        long_content = "A" * 200
        nodes = [_node("test", long_content)]
        result = m.generate(nodes)
        assert "..." in result
        assert len(result) < 200

    def test_cache_returns_same_result(self):
        m = MemoryManifest()
        nodes = [_node("cached")]
        r1 = m.generate_cached(nodes)
        r2 = m.generate_cached(nodes)
        assert r1 == r2

    def test_invalidate_cache(self):
        m = MemoryManifest()
        m._cache["test"] = (0, "old")
        m.invalidate_cache()
        assert m._cache == {}
