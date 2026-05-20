"""Tests for domain expansion."""

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.read.domain_expansion import filter_by_domain, find_related_by_tags


def _node(node_id, tags=None, domains=None):
    return MemoryNode(
        id=node_id, name=f"node-{node_id}", content="content",
        tags=tags or [], applicable_domains=domains or [],
    )


class TestFindRelatedByTags:
    def test_finds_nodes_with_overlapping_tags(self):
        anchors = [_node("a1", tags=["python", "aws", "lambda"])]
        all_nodes = [
            _node("b1", tags=["python", "aws", "docker"]),
            _node("b2", tags=["python", "react"]),
            _node("b3", tags=["java", "spring"]),
        ]
        result = find_related_by_tags(anchors, all_nodes, min_tag_overlap=2)
        ids = {n.id for n in result}
        assert "b1" in ids  # 2 tags overlap: python, aws
        assert "b2" not in ids  # only 1 tag overlap
        assert "b3" not in ids

    def test_excludes_anchor_nodes(self):
        anchors = [_node("a1", tags=["python", "aws"])]
        all_nodes = [_node("a1", tags=["python", "aws"])]
        result = find_related_by_tags(anchors, all_nodes, min_tag_overlap=1)
        assert result == []

    def test_excludes_specified_ids(self):
        anchors = [_node("a1", tags=["python", "aws"])]
        all_nodes = [_node("b1", tags=["python", "aws"])]
        result = find_related_by_tags(anchors, all_nodes, min_tag_overlap=1, exclude_ids={"b1"})
        assert result == []

    def test_case_insensitive(self):
        anchors = [_node("a1", tags=["Python", "AWS"])]
        all_nodes = [_node("b1", tags=["python", "aws"])]
        result = find_related_by_tags(anchors, all_nodes, min_tag_overlap=2)
        assert len(result) == 1

    def test_empty_anchors(self):
        all_nodes = [_node("b1", tags=["python"])]
        result = find_related_by_tags([], all_nodes, min_tag_overlap=1)
        assert result == []


class TestFilterByDomain:
    def test_no_domain_returns_all(self):
        memories = [_node("n1", domains=["git"]), _node("n2")]
        result = filter_by_domain(memories, active_domain=None)
        assert len(result) == 2

    def test_filters_to_matching_domain(self):
        memories = [
            _node("git-only", domains=["git"]),
            _node("npm-only", domains=["npm"]),
            _node("universal", domains=[]),
        ]
        result = filter_by_domain(memories, active_domain="git")
        ids = {n.id for n in result}
        assert "git-only" in ids
        assert "universal" in ids
        assert "npm-only" not in ids

    def test_case_insensitive_domain(self):
        memories = [_node("n1", domains=["Git"])]
        result = filter_by_domain(memories, active_domain="GIT")
        assert len(result) == 1

    def test_empty_memories(self):
        result = filter_by_domain([], active_domain="git")
        assert result == []
