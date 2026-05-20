"""Temporal decay functions for memory scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum


class DecayModel(str, Enum):
    EBBINGHAUS = "ebbinghaus"
    POWER_LAW = "power_law"
    EXPONENTIAL = "exponential"
    GAUSSIAN = "gaussian"


def ebbinghaus_decay(hours_since_access: float, strength: float = 1.0, half_life_hours: float = 336.0) -> float:
    """Ebbinghaus forgetting curve: R = e^(-t / stability).

    stability is derived from half_life and strength so that at t=half_life,
    R = 0.5 when strength=1.0.
    """
    strength = max(0.01, strength)
    half_life_hours = max(0.01, half_life_hours)
    stability = (half_life_hours * strength) / math.log(2)
    return math.exp(-max(0.0, hours_since_access) / stability)


def power_law_decay(hours_since_access: float, strength: float = 1.0, exponent: float = 0.6) -> float:
    """Power-law decay: score = strength / (1 + t)^exponent, clamped to [0, 1].

    Inspired by CortexGraph: (use_count+1)^0.6 * decay(dt) * strength.
    """
    raw = strength / ((1.0 + max(0.0, hours_since_access)) ** exponent)
    return min(1.0, raw)


def exponential_decay(hours_since_access: float, half_life_hours: float = 336.0) -> float:
    """Simple exponential decay with configurable half-life (default 14 days)."""
    half_life_hours = max(0.01, half_life_hours)
    return math.exp(-math.log(2) * max(0.0, hours_since_access) / half_life_hours)


def compute_decay(
    last_accessed: datetime,
    model: DecayModel | str = DecayModel.EBBINGHAUS,
    strength: float = 1.0,
    half_life_hours: float = 336.0,
) -> float:
    """Compute current decay score for a memory node."""
    now = datetime.now(timezone.utc)
    hours = max(0.0, (now - last_accessed).total_seconds() / 3600.0)

    if model == DecayModel.EBBINGHAUS:
        return ebbinghaus_decay(hours, strength, half_life_hours)
    elif model == DecayModel.POWER_LAW:
        return power_law_decay(hours, strength)
    elif model == DecayModel.EXPONENTIAL:
        return exponential_decay(hours, half_life_hours)
    elif model == DecayModel.GAUSSIAN:
        return gaussian_recency(hours, scale_hours=half_life_hours)
    else:
        raise ValueError(f"Unknown decay model: {model}")


def heat_score(
    visits: int,
    interaction_len: float,
    hours_since: float,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.0,
    tau_hours: float = 24.0,
) -> float:
    """Heat-based scoring combining frequency, engagement, and recency.

    Adapted from MemoryOS (Apache 2.0) three-signal formula.
    """
    recency = math.exp(-max(0.0, hours_since) / max(0.01, tau_hours))
    return alpha * visits + beta * interaction_len + gamma * recency


def composite_score(
    use_count: int,
    hours_since: float,
    strength: float = 1.0,
    beta: float = 0.6,
    decay_model: str = "power_law",
) -> float:
    """CortexGraph-inspired composite: usage amplification × temporal decay × strength.

    Clean-room reimplementation of the architectural idea.
    """
    use_component = math.pow(max(use_count, 0) + 1, beta)
    if decay_model == "power_law":
        decay_component = power_law_decay(hours_since, strength=1.0)
    else:
        decay_component = exponential_decay(hours_since)
    return use_component * decay_component * strength


def gaussian_recency(
    age_hours: float,
    scale_hours: float = 168.0,
    decay_factor: float = 0.5,
) -> float:
    """Gaussian decay for query-time recency scoring.

    Inspired by AgentCore's OpenSearch function_score pattern.
    Returns 1.0 at age=0, dropping to exp(-decay_factor) at age=scale_hours.
    With default decay_factor=0.5, value at scale_hours ≈ 0.607.
    """
    if scale_hours <= 0:
        return 0.0
    return math.exp(-decay_factor * (max(0.0, age_hours) / scale_hours) ** 2)
