"""Tests for Beta distribution confidence model."""

import pytest

from agent_memory_fabric.lifecycle.confidence import BetaConfidence


class TestFromProvenance:
    def test_user_explicit_high_confidence(self):
        c = BetaConfidence.from_provenance("user_explicit")
        assert c.base_confidence == pytest.approx(0.9, abs=0.01)

    def test_inferred_neutral(self):
        c = BetaConfidence.from_provenance("inferred")
        assert c.base_confidence == pytest.approx(0.5, abs=0.01)

    def test_synthesized_moderate(self):
        c = BetaConfidence.from_provenance("synthesized")
        assert c.base_confidence == pytest.approx(0.6, abs=0.01)


class TestRecordOutcome:
    def test_success_increases_confidence(self):
        c = BetaConfidence()
        before = c.base_confidence
        c.record_outcome(success=True)
        assert c.base_confidence > before

    def test_failure_decreases_confidence(self):
        c = BetaConfidence()
        before = c.base_confidence
        c.record_outcome(success=False)
        assert c.base_confidence < before

    def test_multiple_successes(self):
        c = BetaConfidence()
        for _ in range(10):
            c.record_outcome(success=True)
        assert c.base_confidence > 0.8

    def test_multiple_failures(self):
        c = BetaConfidence()
        for _ in range(10):
            c.record_outcome(success=False)
        assert c.base_confidence < 0.2

    def test_weighted_outcome(self):
        c1 = BetaConfidence()
        c2 = BetaConfidence()
        c1.record_outcome(success=True, weight=1.0)
        c2.record_outcome(success=True, weight=5.0)
        assert c2.base_confidence > c1.base_confidence

    def test_sliding_window(self):
        c = BetaConfidence()
        for _ in range(20):
            c.record_outcome(success=True)
        assert len(c.recent_outcomes) == 15


class TestEffectiveConfidence:
    def test_no_outcomes_equals_base(self):
        c = BetaConfidence(alpha=3.0, beta_param=1.0)
        assert c.effective_confidence() == c.base_confidence

    def test_recent_successes_boost(self):
        c = BetaConfidence(alpha=1.0, beta_param=1.0)
        for _ in range(5):
            c.record_outcome(success=True)
        assert c.effective_confidence() > 0.5

    def test_recent_failures_reduce(self):
        c = BetaConfidence(alpha=5.0, beta_param=1.0)
        for _ in range(5):
            c.record_outcome(success=False)
        eff = c.effective_confidence()
        assert eff < c.base_confidence

    def test_bounded_zero_one(self):
        c = BetaConfidence(alpha=0.01, beta_param=100.0)
        for _ in range(15):
            c.record_outcome(success=False)
        assert 0.0 <= c.effective_confidence() <= 1.0

        c2 = BetaConfidence(alpha=100.0, beta_param=0.01)
        for _ in range(15):
            c2.record_outcome(success=True)
        assert 0.0 <= c2.effective_confidence() <= 1.0

    def test_recency_weight_controls_blend(self):
        c = BetaConfidence(alpha=1.0, beta_param=9.0)
        for _ in range(10):
            c.record_outcome(success=True)
        low_recency = c.effective_confidence(recency_weight=0.1)
        high_recency = c.effective_confidence(recency_weight=0.9)
        assert high_recency > low_recency


class TestPhase3Interface:
    def test_should_accelerate_decay_when_low(self):
        c = BetaConfidence(alpha=1.0, beta_param=9.0)
        assert c.should_accelerate_decay() is True

    def test_should_not_accelerate_when_moderate(self):
        c = BetaConfidence(alpha=1.0, beta_param=1.0)
        assert c.should_accelerate_decay() is False

    def test_should_resist_when_high(self):
        c = BetaConfidence(alpha=9.0, beta_param=1.0)
        assert c.should_resist_transition() is True

    def test_should_not_resist_when_moderate(self):
        c = BetaConfidence(alpha=1.0, beta_param=1.0)
        assert c.should_resist_transition() is False

    def test_accelerate_and_resist_mutually_exclusive(self):
        c = BetaConfidence(alpha=1.0, beta_param=1.0)
        assert not (c.should_accelerate_decay() and c.should_resist_transition())


class TestOutcomeCount:
    def test_starts_at_zero(self):
        c = BetaConfidence()
        assert c.outcome_count == 0

    def test_increments(self):
        c = BetaConfidence()
        c.record_outcome(success=True)
        c.record_outcome(success=False)
        assert c.outcome_count == 2
