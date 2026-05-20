"""Temporal decay functions for memory scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum


class DecayModel(str, Enum):
    EBBINGHAUS = "ebbinghaus"
    POWER_LAW = "power_law"
    EXPONENTIAL = "exponential"


def ebbinghaus_decay(hours_since_access: float, strength: float = 1.0) -> float:
    """Ebbinghaus forgetting curve: R = e^(-t / (S * stability))."""
    stability = strength * 24.0  # strength=1.0 → 24h half-point
    return math.exp(-hours_since_access / stability)


def power_law_decay(hours_since_access: float, strength: float = 1.0, exponent: float = 0.6) -> float:
    """Power-law decay: score = strength / (1 + t)^exponent, clamped to [0, 1].

    Inspired by CortexGraph: (use_count+1)^0.6 * decay(dt) * strength.
    """
    raw = strength / ((1.0 + max(0.0, hours_since_access)) ** exponent)
    return min(1.0, raw)


def exponential_decay(hours_since_access: float, half_life_hours: float = 336.0) -> float:
    """Simple exponential decay with configurable half-life (default 14 days)."""
    return math.exp(-0.693 * hours_since_access / half_life_hours)


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
        return ebbinghaus_decay(hours, strength)
    elif model == DecayModel.POWER_LAW:
        return power_law_decay(hours, strength)
    elif model == DecayModel.EXPONENTIAL:
        return exponential_decay(hours, half_life_hours)
    else:
        raise ValueError(f"Unknown decay model: {model}")
