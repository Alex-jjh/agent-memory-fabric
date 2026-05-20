"""Tests for graph operations (wikilinks, PPR, BFS)."""

import pytest

from agent_memory_fabric.storage.graph import (
    build_edges_from_wikilinks,
    extract_wikilinks,
    get_subgraph_bfs,
    personalized_pagerank,
)


class TestExtractWikilinks:
    def test_basic(self):
        assert extract_wikilinks("See [[note-a]] here") == ["note-a"]

    def test_multiple(self):
        assert extract_wikilinks("[[a]] and [[b]]") == ["a", "b"]

    def test_none(self):
        assert extract_wikilinks("no links") == []

    def test_with_spaces(self):
        assert extract_wikilinks("[[my note]]") == ["my note"]

    def test_ignores_single_brackets(self):
        assert extract_wikilinks("[not a link] but [[real]]") == ["real"]


class TestBuildEdgesFromWikilinks:
    def test_resolves_known_targets(self):
        name_to_id = {"target-a": "id-a", "target-b": "id-b"}
        edges = build_edges_from_wikilinks(
            "source-id", "Links to [[target-a]] and [[target-b]]", name_to_id
        )
        assert len(edges) == 2
        assert edges[0] == ("source-id", "id-a", "links_to", 1.0)

    def test_skips_unknown_targets(self):
        name_to_id = {"known": "id-1"}
        edges = build_edges_from_wikilinks(
            "source-id", "[[known]] and [[unknown]]", name_to_id
        )
        assert len(edges) == 1

    def test_skips_self_links(self):
        name_to_id = {"self": "my-id"}
        edges = build_edges_from_wikilinks("my-id", "[[self]]", name_to_id)
        assert edges == []


class TestPersonalizedPageRank:
    def test_single_node(self):
        scores = personalized_pagerank([], {"a": 1.0})
        assert scores["a"] == 1.0

    def test_two_connected_nodes(self):
        edges = [("a", "b", 1.0), ("b", "a", 1.0)]
        scores = personalized_pagerank(edges, {"a": 1.0})
        assert scores["a"] > scores["b"]

    def test_seed_node_has_highest_score(self):
        edges = [("a", "b", 1.0), ("b", "c", 1.0), ("c", "a", 1.0)]
        scores = personalized_pagerank(edges, {"a": 1.0})
        assert scores["a"] >= scores["b"]
        assert scores["a"] >= scores["c"]

    def test_scores_are_normalized(self):
        edges = [("a", "b", 1.0), ("b", "c", 1.0), ("a", "c", 0.5)]
        scores = personalized_pagerank(edges, {"a": 1.0})
        assert max(scores.values()) == pytest.approx(1.0)

    def test_multiple_seeds(self):
        edges = [("a", "c", 1.0), ("b", "c", 1.0)]
        scores = personalized_pagerank(edges, {"a": 0.5, "b": 0.5})
        assert scores["c"] > 0

    def test_empty_seeds(self):
        assert personalized_pagerank([("a", "b", 1.0)], {}) == {}

    def test_disconnected_nodes(self):
        edges = [("a", "b", 1.0)]
        scores = personalized_pagerank(edges, {"a": 1.0})
        assert "a" in scores
        assert "b" in scores
        assert scores["a"] > scores["b"]

    def test_five_node_graph(self):
        edges = [
            ("a", "b", 1.0),
            ("b", "c", 1.0),
            ("c", "d", 1.0),
            ("d", "e", 1.0),
            ("e", "a", 1.0),
        ]
        scores = personalized_pagerank(edges, {"a": 1.0}, alpha=0.85)
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        assert sorted_nodes[0][0] == "a"


class TestGetSubgraphBFS:
    def test_depth_zero(self):
        result = get_subgraph_bfs("a", lambda _: [], depth=0)
        assert result == {"a"}

    def test_depth_one(self):
        neighbors = {"a": ["b", "c"], "b": ["d"], "c": [], "d": []}
        result = get_subgraph_bfs("a", lambda n: neighbors.get(n, []), depth=1)
        assert result == {"a", "b", "c"}

    def test_depth_two(self):
        neighbors = {"a": ["b", "c"], "b": ["d"], "c": [], "d": ["e"], "e": []}
        result = get_subgraph_bfs("a", lambda n: neighbors.get(n, []), depth=2)
        assert result == {"a", "b", "c", "d"}

    def test_cycle_handling(self):
        neighbors = {"a": ["b"], "b": ["c"], "c": ["a"]}
        result = get_subgraph_bfs("a", lambda n: neighbors.get(n, []), depth=10)
        assert result == {"a", "b", "c"}

    def test_isolated_node(self):
        result = get_subgraph_bfs("lonely", lambda _: [], depth=5)
        assert result == {"lonely"}
