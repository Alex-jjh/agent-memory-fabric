"""Beta distribution confidence model for memory nodes.

Inspired by Quick Desktop's Bayesian confidence (clean-room implementation)
and Cognee's streaming update formula (Apache 2.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

import math

RECENCY_DECAY = 0.8
MAX_RECENT_OUTCOMES = 15
ACCELERATE_DECAY_THRESHOLD = 0.3
RESIST_TRANSITION_THRESHOLD = 0.8
ANTI_PATTERN_CAP = 0.6
BASE_WEIGHT = 0.7
RECENT_WEIGHT = 0.3


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

    is_anti_pattern: bool = Field(default=False)

    @classmethod
    def from_provenance(cls, provenance: str, is_anti_pattern: bool = False) -> BetaConfidence:
        """Create confidence prior based on how the memory was created."""
        priors = {
            "user_explicit": (9.0, 1.0),
            "synthesized": (3.0, 2.0),
            "inferred": (3.0, 7.0),
            "inferred_high": (5.0, 5.0),
        }
        alpha, beta = priors.get(provenance, (1.0, 1.0))
        return cls(alpha=alpha, beta_param=beta, is_anti_pattern=is_anti_pattern)

    @property
    def base_confidence(self) -> float:
        """Mean of the Beta distribution."""
        total = self.alpha + self.beta_param
        if total <= 0:
            return 0.5
        return self.alpha / total

    def record_outcome(self, success: bool, weight: float = 1.0) -> None:
        """Record an observation about this memory's usefulness."""
        weight = max(0.0, weight)
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
        """Blended confidence using weighted geometric mean.

        Formula: base^0.7 * max(recent, 0.01)^0.3
        Anti-patterns are capped at ANTI_PATTERN_CAP (0.6).
        """
        base = max(self.base_confidence, 0.01)

        if not self.recent_outcomes:
            result = base
        else:
            recent_score = max(self._compute_recent_ema(), 0.01)
            result = math.pow(base, BASE_WEIGHT) * math.pow(recent_score, RECENT_WEIGHT)

        if self.is_anti_pattern:
            result = min(result, ANTI_PATTERN_CAP)

        return max(0.0, min(1.0, result))

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


class MutationLedger:
    """Tracks confidence mutations to enforce max 1 per node per cycle."""

    def __init__(self):
        self._mutated: set[str] = set()

    def can_mutate(self, node_id: str) -> bool:
        return node_id not in self._mutated

    def record(self, node_id: str) -> None:
        self._mutated.add(node_id)

    def reset(self) -> None:
        self._mutated.clear()

    @property
    def count(self) -> int:
        return len(self._mutated)
