"""Tests for multi-signal scorer."""

from datetime import datetime, timedelta, timezone

import pytest

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.read.scorer import (
    MultiSignalScorer,
    normalize_bm25,
    normalize_frequency,
    reciprocal_rank_fusion,
)


class TestNormalizeBM25:
    def test_zero_returns_low(self):
        assert normalize_bm25(0.0) < 0.01

    def test_high_score_near_one(self):
        assert normalize_bm25(20.0) > 0.99

    def test_midpoint_returns_half(self):
        assert abs(normalize_bm25(8.0) - 0.5) < 0.01

    def test_monotonically_increasing(self):
        scores = [normalize_bm25(x) for x in range(0, 20)]
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1]

    def test_output_bounded(self):
        for x in [-10, 0, 5, 10, 50, 100]:
            score = normalize_bm25(float(x))
            assert 0.0 <= score <= 1.0


class TestNormalizeFrequency:
    def test_zero_access(self):
        assert normalize_frequency(0) == 0.0

    def test_one_access(self):
        score = normalize_frequency(1)
        assert 0.0 < score < 0.5

    def test_high_access(self):
        score = normalize_frequency(99)
        assert score > 0.9

    def test_capped_at_one(self):
        assert normalize_frequency(10000) == 1.0


class TestReciprocalRankFusion:
    def test_single_list(self):
        results = reciprocal_rank_fusion([[("a", 10.0), ("b", 5.0), ("c", 1.0)]])
        ids = [r[0] for r in results]
        assert ids == ["a", "b", "c"]

    def test_two_lists_agreement(self):
        list1 = [("a", 10.0), ("b", 5.0)]
        list2 = [("a", 8.0), ("b", 3.0)]
        results = reciprocal_rank_fusion([list1, list2])
        assert results[0][0] == "a"

    def test_two_lists_boost_overlap(self):
        list1 = [("a", 10.0), ("b", 5.0)]
        list2 = [("b", 10.0), ("c", 5.0)]
        results = reciprocal_rank_fusion([list1, list2])
        ids = [r[0] for r in results]
        assert "b" in ids[:2]

    def test_empty_lists(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[]]) == []

    def test_disjoint_lists(self):
        list1 = [("a", 10.0)]
        list2 = [("b", 10.0)]
        results = reciprocal_rank_fusion([list1, list2])
        assert len(results) == 2
        assert results[0][1] == results[1][1]


def _make_node(name, hours_ago=0, access_count=0, state=LifecycleState.ACTIVE):
    now = datetime.now(timezone.utc)
    return MemoryNode(
        name=name,
        content=f"Content of {name}",
        state=state,
        last_accessed=now - timedelta(hours=hours_ago),
        access_count=access_count,
    )


class TestMultiSignalScorer:
    def setup_method(self):
        self.scorer = MultiSignalScorer()

    def test_recent_scores_higher(self):
        recent = _make_node("recent", hours_ago=1)
        old = _make_node("old", hours_ago=72 * 24)
        scored = self.scorer.score([recent, old])
        assert scored[0].node.name == "recent"

    def test_frequent_scores_higher(self):
        popular = _make_node("popular", access_count=50)
        unused = _make_node("unused", access_count=0)
        scored = self.scorer.score([popular, unused])
        assert scored[0].node.name == "popular"

    def test_bm25_boost(self):
        n1 = _make_node("match")
        n2 = _make_node("no-match")
        fts = {n1.id: 12.0}
        scored = self.scorer.score([n1, n2], fts_scores=fts)
        assert scored[0].node.name == "match"

    def test_state_filter_excludes_expired(self):
        active = _make_node("active")
        expired = _make_node("expired", state=LifecycleState.EXPIRED)
        scored = self.scorer.score([active, expired])
        assert len(scored) == 1
        assert scored[0].node.name == "active"

    def test_state_filter_excludes_archived(self):
        active = _make_node("active")
        archived = _make_node("archived", state=LifecycleState.ARCHIVED)
        scored = self.scorer.score([active, archived])
        assert len(scored) == 1

    def test_custom_state_filter(self):
        archived = _make_node("archived", state=LifecycleState.ARCHIVED)
        scored = self.scorer.score(
            [archived],
            state_filter={LifecycleState.ACTIVE, LifecycleState.DECIDED, LifecycleState.ARCHIVED},
        )
        assert len(scored) == 1

    def test_tier_assignment(self):
        nodes = [_make_node(f"n{i}", hours_ago=i * 10) for i in range(10)]
        scored = self.scorer.score(nodes)
        tiers = [s.tier for s in scored]
        assert "hot" in tiers
        assert "warm" in tiers
        assert "cold" in tiers

    def test_signal_breakdown_present(self):
        node = _make_node("test", access_count=5)
        scored = self.scorer.score([node], fts_scores={node.id: 10.0})
        assert "bm25" in scored[0].signal_breakdown
        assert "recency" in scored[0].signal_breakdown
        assert "frequency" in scored[0].signal_breakdown

    def test_empty_candidates(self):
        assert self.scorer.score([]) == []
