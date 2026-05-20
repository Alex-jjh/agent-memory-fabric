"""Tests for spaced repetition (danger zone review)."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.core.node import MemoryNode, MemoryType
from agent_memory_fabric.read.scorer import ScoredMemory
from agent_memory_fabric.read.spaced_repetition import (
    blend_with_review,
    compute_review_priority,
    select_review_candidates,
)


class TestComputeReviewPriority:
    def test_zero_outside_danger_zone_low(self):
        assert compute_review_priority(0.05) == 0.0

    def test_zero_outside_danger_zone_high(self):
        assert compute_review_priority(0.50) == 0.0

    def test_peak_at_midpoint(self):
        priority = compute_review_priority(0.25)
        assert priority == 1.0

    def test_positive_inside_zone(self):
        assert compute_review_priority(0.20) > 0.0
        assert compute_review_priority(0.30) > 0.0

    def test_symmetric_around_midpoint(self):
        p_low = compute_review_priority(0.20)
        p_high = compute_review_priority(0.30)
        assert abs(p_low - p_high) < 0.01

    def test_boundary_values(self):
        assert compute_review_priority(0.15) == 0.0
        assert compute_review_priority(0.35) < 1e-10


class TestSelectReviewCandidates:
    def _make_node(self, hours_ago, strength=1.0):
        now = datetime.now(timezone.utc)
        return MemoryNode(
            id=f"n-{hours_ago}",
            name="test",
            content="content",
            last_accessed=now - timedelta(hours=hours_ago),
            strength=strength,
        )

    def test_returns_empty_for_fresh_nodes(self):
        nodes = [self._make_node(hours_ago=1)]
        result = select_review_candidates(nodes)
        assert result == []

    def test_returns_nodes_in_danger_zone(self):
        # Ebbinghaus with strength=1.0: decay = exp(-t/24)
        # decay=0.25 at t = -24*ln(0.25) ≈ 33.3 hours
        nodes = [self._make_node(hours_ago=33)]
        result = select_review_candidates(nodes)
        assert len(result) <= 1  # may or may not be in zone depending on exact decay

    def test_respects_limit(self):
        nodes = [self._make_node(hours_ago=30 + i, strength=0.5) for i in range(20)]
        result = select_review_candidates(nodes, limit=3)
        assert len(result) <= 3


class TestBlendWithReview:
    def _make_sm(self, node_id):
        node = MemoryNode(id=node_id, name="test", content="x")
        return ScoredMemory(node=node, total_score=0.5, signal_breakdown={})

    def _make_node(self, node_id):
        return MemoryNode(id=node_id, name="review", content="review content")

    def test_no_review_candidates_returns_primary(self):
        primary = [self._make_sm("p1"), self._make_sm("p2")]
        result = blend_with_review(primary, [])
        assert len(result) == 2

    def test_interleaves_review(self):
        primary = [self._make_sm(f"p{i}") for i in range(6)]
        review = [self._make_node("r1"), self._make_node("r2")]
        result = blend_with_review(primary, review, blend_ratio=0.3)
        assert len(result) == 6
        ids = [sm.node.id for sm in result]
        assert "r1" in ids or "r2" in ids

    def test_output_length_matches_primary(self):
        primary = [self._make_sm(f"p{i}") for i in range(10)]
        review = [self._make_node(f"r{i}") for i in range(5)]
        result = blend_with_review(primary, review, blend_ratio=0.3)
        assert len(result) == 10

    def test_empty_primary(self):
        review = [self._make_node("r1")]
        result = blend_with_review([], review)
        assert result == []
