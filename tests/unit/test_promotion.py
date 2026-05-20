"""Tests for PromotionPredicate."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.transitions import PromotionPredicate


def _make_node(
    state=LifecycleState.ACTIVE,
    access_count=0,
    created_days_ago=0,
    last_accessed_hours_ago=0,
    strength=1.0,
) -> MemoryNode:
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id="test-promo",
        name="test",
        content="test content for promotion",
        state=state,
        access_count=access_count,
        created=now - timedelta(days=created_days_ago),
        last_accessed=now - timedelta(hours=last_accessed_hours_ago),
        strength=strength,
    )


class TestPromotionPredicate:
    def test_ignores_non_active_nodes(self):
        pred = PromotionPredicate()
        node = _make_node(state=LifecycleState.DECIDED)
        assert pred.evaluate(node) is None

    def test_promotes_high_score_node(self):
        pred = PromotionPredicate(score_threshold=0.5, min_age_days=1.0)
        node = _make_node(last_accessed_hours_ago=0, strength=2.0, access_count=3, created_days_ago=2)
        result = pred.evaluate(node)
        assert result == LifecycleState.DECIDED

    def test_does_not_promote_too_young(self):
        pred = PromotionPredicate(score_threshold=0.5, min_age_days=2.0)
        node = _make_node(last_accessed_hours_ago=0, strength=2.0, access_count=5, created_days_ago=1)
        assert pred.evaluate(node) is None

    def test_does_not_promote_low_score(self):
        pred = PromotionPredicate(score_threshold=0.99, min_age_days=0)
        node = _make_node(last_accessed_hours_ago=48, access_count=1, created_days_ago=30)
        assert pred.evaluate(node) is None

    def test_promotes_by_access_count_in_window(self):
        pred = PromotionPredicate(score_threshold=0.99, access_threshold=5, window_days=14, min_age_days=0)
        node = _make_node(access_count=5, created_days_ago=10, last_accessed_hours_ago=48)
        result = pred.evaluate(node)
        assert result == LifecycleState.DECIDED

    def test_access_count_outside_window_not_promoted(self):
        pred = PromotionPredicate(score_threshold=0.99, access_threshold=5, window_days=14, min_age_days=0)
        node = _make_node(access_count=10, created_days_ago=30, last_accessed_hours_ago=48)
        assert pred.evaluate(node) is None

    def test_below_access_threshold_not_promoted(self):
        pred = PromotionPredicate(score_threshold=0.99, access_threshold=5, window_days=14, min_age_days=0)
        node = _make_node(access_count=3, created_days_ago=7, last_accessed_hours_ago=72)
        assert pred.evaluate(node) is None

    def test_default_thresholds(self):
        pred = PromotionPredicate()
        assert pred.score_threshold == 0.65
        assert pred.access_threshold == 5
        assert pred.window_days == 14
