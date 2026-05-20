"""Tests for decay functions."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.lifecycle.decay import (
    DecayModel,
    compute_decay,
    ebbinghaus_decay,
    exponential_decay,
    power_law_decay,
)


def test_ebbinghaus_fresh_memory():
    score = ebbinghaus_decay(0.0, strength=1.0)
    assert score == 1.0


def test_ebbinghaus_decays_over_time():
    score_1h = ebbinghaus_decay(1.0)
    score_24h = ebbinghaus_decay(24.0)
    score_168h = ebbinghaus_decay(168.0)  # 7 days
    assert score_1h > score_24h > score_168h


def test_ebbinghaus_strength_slows_decay():
    weak = ebbinghaus_decay(48.0, strength=1.0)
    strong = ebbinghaus_decay(48.0, strength=2.0)
    assert strong > weak


def test_power_law_fresh():
    score = power_law_decay(0.0)
    assert score == 1.0


def test_power_law_decays():
    assert power_law_decay(24.0) < power_law_decay(1.0)


def test_exponential_half_life():
    half_life = 336.0  # 14 days in hours
    score = exponential_decay(half_life, half_life_hours=half_life)
    assert abs(score - 0.5) < 0.01


def test_compute_decay_dispatch():
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    old = datetime.now(timezone.utc) - timedelta(days=30)

    recent_score = compute_decay(recent, model=DecayModel.EBBINGHAUS)
    old_score = compute_decay(old, model=DecayModel.EBBINGHAUS)
    assert recent_score > old_score
