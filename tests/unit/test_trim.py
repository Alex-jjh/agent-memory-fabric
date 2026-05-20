"""Tests for AutoTrimmer."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType
from agent_memory_fabric.lifecycle.trim import (
    AutoTrimmer,
    compute_trim_score,
    recency_sigmoid,
)


def _make_node(
    id="t1",
    access_count=0,
    confidence_alpha=1.0,
    confidence_beta=1.0,
    last_accessed_days_ago=0,
    tags=None,
    node_type=MemoryType.PROJECT,
) -> MemoryNode:
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=id,
        name=f"node-{id}",
        content="test content",
        type=node_type,
        access_count=access_count,
        confidence_alpha=confidence_alpha,
        confidence_beta=confidence_beta,
        last_accessed=now - timedelta(days=last_accessed_days_ago),
        tags=tags or [],
    )


class TestRecencySigmoid:
    def test_at_zero(self):
        score = recency_sigmoid(0.0, halflife_seconds=30 * 86400)
        assert score > 0.95

    def test_at_halflife(self):
        halflife = 30 * 86400.0
        score = recency_sigmoid(halflife, halflife)
        assert abs(score - 0.5) < 0.01

    def test_very_old(self):
        halflife = 30 * 86400.0
        score = recency_sigmoid(halflife * 3, halflife)
        assert score < 0.1

    def test_zero_halflife(self):
        assert recency_sigmoid(100.0, 0.0) == 0.0


class TestComputeTrimScore:
    def test_high_confidence_high_score(self):
        node = _make_node(confidence_alpha=9.0, confidence_beta=1.0, last_accessed_days_ago=0)
        score = compute_trim_score(node)
        assert score > 0.5

    def test_low_confidence_old_low_score(self):
        node = _make_node(confidence_alpha=1.0, confidence_beta=9.0, last_accessed_days_ago=90)
        score = compute_trim_score(node)
        assert score < 0.3

    def test_recent_beats_old(self):
        recent = _make_node(id="r", last_accessed_days_ago=1)
        old = _make_node(id="o", last_accessed_days_ago=60)
        assert compute_trim_score(recent) > compute_trim_score(old)


class TestAutoTrimmer:
    def test_needs_trim_below_limit(self):
        trimmer = AutoTrimmer(max_count=100)
        assert trimmer.needs_trim(50) is False

    def test_needs_trim_above_limit(self):
        trimmer = AutoTrimmer(max_count=100)
        assert trimmer.needs_trim(150) is True

    def test_select_for_trim_excludes_protected(self):
        trimmer = AutoTrimmer(max_count=5, trim_ratio=0.5)
        nodes = [
            _make_node(id="protected", node_type=MemoryType.USER, last_accessed_days_ago=90),
            _make_node(id="old1", last_accessed_days_ago=60),
            _make_node(id="old2", last_accessed_days_ago=60),
            _make_node(id="fresh", last_accessed_days_ago=0, confidence_alpha=9.0),
        ]
        to_trim = trimmer.select_for_trim(nodes)
        trimmed_ids = {n.id for n in to_trim}
        assert "protected" not in trimmed_ids

    def test_select_trims_lowest_scores(self):
        trimmer = AutoTrimmer(max_count=5, trim_ratio=0.25)
        nodes = [
            _make_node(id="best", last_accessed_days_ago=0, confidence_alpha=9.0),
            _make_node(id="mid", last_accessed_days_ago=15),
            _make_node(id="worst1", last_accessed_days_ago=90, confidence_alpha=1.0, confidence_beta=9.0),
            _make_node(id="worst2", last_accessed_days_ago=90, confidence_alpha=1.0, confidence_beta=9.0),
        ]
        to_trim = trimmer.select_for_trim(nodes)
        trimmed_ids = {n.id for n in to_trim}
        assert "best" not in trimmed_ids
        assert len(to_trim) >= 1
