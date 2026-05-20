"""Beta distribution confidence model for memory nodes.

Inspired by Quick Desktop's Bayesian confidence (clean-room implementation)
and Cognee's streaming update formula (Apache 2.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

RECENCY_DECAY = 0.8
MAX_RECENT_OUTCOMES = 15
ACCELERATE_DECAY_THRESHOLD = 0.3
RESIST_TRANSITION_THRESHOLD = 0.8


@dataclass
class Outcome:
    success: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    weight: float = 1.0


class BetaConfidence(BaseModel):
    """Bayesian confidence tracker using Beta distribution.

    The Beta(alpha, beta) distribution models uncertainty about a memory's
    reliability. alpha counts "successes" (memory was useful/confirmed),
    beta counts "failures" (memory was wrong/unhelpful).

    Mean confidence = alpha / (alpha + beta).
    """

    alpha: float = Field(default=1.0, ge=0.01)
    beta_param: float = Field(default=1.0, ge=0.01)
    recent_outcomes: list[dict] = Field(default_factory=list)

    @classmethod
    def from_provenance(cls, provenance: str) -> BetaConfidence:
        """Create confidence prior based on how the memory was created.

        - user_explicit: User directly stated this (high prior, ~0.9)
        - inferred: System inferred from context (neutral prior, ~0.5)
        - synthesized: Auto-generated summary (moderate prior, ~0.6)
        """
        if provenance == "user_explicit":
            return cls(alpha=9.0, beta_param=1.0)
        elif provenance == "synthesized":
            return cls(alpha=3.0, beta_param=2.0)
        else:
            return cls(alpha=1.0, beta_param=1.0)

    @property
    def base_confidence(self) -> float:
        """Mean of the Beta distribution."""
        return self.alpha / (self.alpha + self.beta_param)

    def record_outcome(self, success: bool, weight: float = 1.0) -> None:
        """Record an observation about this memory's usefulness."""
        if success:
            self.alpha += weight
        else:
            self.beta_param += weight

        outcome = {
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "weight": weight,
        }
        self.recent_outcomes.append(outcome)
        if len(self.recent_outcomes) > MAX_RECENT_OUTCOMES:
            self.recent_outcomes = self.recent_outcomes[-MAX_RECENT_OUTCOMES:]

    def effective_confidence(self, recency_weight: float = 0.3) -> float:
        """Blended confidence combining base prior + recent outcomes.

        Formula: (1 - recency_weight) * base + recency_weight * recent_ema
        """
        base = self.base_confidence

        if not self.recent_outcomes:
            return base

        recent_score = self._compute_recent_ema()
        blended = (1.0 - recency_weight) * base + recency_weight * recent_score
        return max(0.0, min(1.0, blended))

    def _compute_recent_ema(self) -> float:
        """Exponentially-weighted moving average of recent outcomes."""
        if not self.recent_outcomes:
            return 0.5

        weighted_sum = 0.0
        weight_total = 0.0
        decay = 1.0

        for outcome in reversed(self.recent_outcomes):
            value = 1.0 if outcome["success"] else 0.0
            w = decay * outcome.get("weight", 1.0)
            weighted_sum += value * w
            weight_total += w
            decay *= RECENCY_DECAY

        if weight_total <= 0:
            return 0.5
        return weighted_sum / weight_total

    def should_accelerate_decay(self) -> bool:
        """Returns True if confidence is low enough to accelerate state transitions.

        Used in Phase 3 to make low-confidence memories transition to
        Archived faster than their temporal decay alone would suggest.
        """
        return self.effective_confidence() < ACCELERATE_DECAY_THRESHOLD

    def should_resist_transition(self) -> bool:
        """Returns True if confidence is high enough to resist state transitions.

        Used in Phase 3 to make high-confidence memories persist in Active/Decided
        state even when temporal decay would normally trigger archival.
        """
        return self.effective_confidence() > RESIST_TRANSITION_THRESHOLD

    @property
    def outcome_count(self) -> int:
        """Total number of observations recorded."""
        return len(self.recent_outcomes)
