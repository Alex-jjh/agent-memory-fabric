"""Tests for decay functions."""

from datetime import datetime, timedelta, timezone

from agent_memory_fabric.lifecycle.decay import (
    DecayModel,
    composite_score,
    compute_decay,
    ebbinghaus_decay,
    exponential_decay,
    gaussian_recency,
    heat_score,
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


# --- B1: Heat Score ---

def test_heat_score_fresh():
    score = heat_score(visits=0, interaction_len=0, hours_since=0.0)
    assert score == 1.0  # gamma * exp(0) = 1.0

def test_heat_score_visits_increase():
    s1 = heat_score(visits=1, interaction_len=0, hours_since=0.0)
    s5 = heat_score(visits=5, interaction_len=0, hours_since=0.0)
    assert s5 > s1

def test_heat_score_decays_with_time():
    fresh = heat_score(visits=3, interaction_len=1.0, hours_since=0.0)
    old = heat_score(visits=3, interaction_len=1.0, hours_since=48.0)
    assert fresh > old

def test_heat_score_interaction_boosts():
    short = heat_score(visits=1, interaction_len=1.0, hours_since=0.0)
    long = heat_score(visits=1, interaction_len=5.0, hours_since=0.0)
    assert long > short


# --- B2: Composite Score ---

def test_composite_score_basic():
    score = composite_score(use_count=0, hours_since=0.0, strength=1.0)
    assert score == 1.0  # (0+1)^0.6 * 1.0 * 1.0 = 1.0

def test_composite_score_high_use_count():
    low = composite_score(use_count=1, hours_since=24.0, strength=1.0)
    high = composite_score(use_count=10, hours_since=24.0, strength=1.0)
    assert high > low

def test_composite_score_strength_amplifies():
    weak = composite_score(use_count=3, hours_since=24.0, strength=0.5)
    strong = composite_score(use_count=3, hours_since=24.0, strength=2.0)
    assert strong > weak

def test_composite_score_power_vs_exponential():
    pl = composite_score(use_count=2, hours_since=48.0, decay_model="power_law")
    exp = composite_score(use_count=2, hours_since=48.0, decay_model="exponential")
    assert pl != exp  # different models yield different scores


# --- B3: Gaussian Recency ---

def test_gaussian_recency_at_zero():
    assert gaussian_recency(age_hours=0.0) == 1.0

def test_gaussian_recency_decays():
    fresh = gaussian_recency(age_hours=24.0, scale_hours=168.0)
    old = gaussian_recency(age_hours=336.0, scale_hours=168.0)
    assert fresh > old

def test_gaussian_recency_at_scale():
    score = gaussian_recency(age_hours=168.0, scale_hours=168.0, decay_factor=0.5)
    # At age=scale, score = exp(-0.5 * 1^2) = exp(-0.5) ≈ 0.606
    assert abs(score - 0.6065) < 0.01

def test_gaussian_recency_zero_scale():
    assert gaussian_recency(age_hours=10.0, scale_hours=0.0) == 0.0
