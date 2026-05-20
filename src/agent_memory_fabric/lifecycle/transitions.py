"""Transition predicates — conditions that trigger state changes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.decay import compute_decay


class TransitionPredicate(Protocol):
    """A predicate that evaluates whether a node should transition."""

    def evaluate(self, node: MemoryNode) -> LifecycleState | None:
        """Returns target state if predicate fires, None otherwise."""
        ...


class TemporalDecayPredicate:
    """Transition to Archived when decay score drops below threshold with no recent access.

    Supports confidence modulation:
    - Low confidence (< 0.3) → accelerates decay (threshold multiplied by 2x)
    - High confidence (> 0.8) → resists decay (threshold multiplied by 0.5x)
    """

    def __init__(self, decay_threshold: float = 0.1, min_inactive_days: int = 14):
        self.decay_threshold = decay_threshold
        self.min_inactive_days = min_inactive_days

    def evaluate(
        self, node: MemoryNode, confidence: float | None = None
    ) -> LifecycleState | None:
        if node.state != LifecycleState.ACTIVE:
            return None

        now = datetime.now(timezone.utc)
        inactive_days = (now - node.last_accessed).total_seconds() / 86400

        effective_min_days = self.min_inactive_days
        effective_threshold = self.decay_threshold

        if confidence is not None:
            if confidence < 0.3:
                effective_min_days = self.min_inactive_days * 0.5
                effective_threshold = self.decay_threshold * 2.0
            elif confidence > 0.8:
                effective_min_days = self.min_inactive_days * 2.0
                effective_threshold = self.decay_threshold * 0.5

        if inactive_days < effective_min_days:
            return None

        decay = compute_decay(node.last_accessed, strength=node.strength)
        if decay < effective_threshold:
            return LifecycleState.ARCHIVED

        return None


class TTLExpirationPredicate:
    """Transition to Expired when TTL is past due."""

    def evaluate(self, node: MemoryNode) -> LifecycleState | None:
        if node.ttl is None:
            return None
        if node.state == LifecycleState.EXPIRED:
            return None

        now = datetime.now(timezone.utc)
        if now > node.ttl:
            return LifecycleState.EXPIRED

        return None


class InactivityArchivePredicate:
    """Transition Decided nodes to Archived after extended inactivity."""

    def __init__(self, inactive_days: int = 30):
        self.inactive_days = inactive_days

    def evaluate(self, node: MemoryNode) -> LifecycleState | None:
        if node.state != LifecycleState.DECIDED:
            return None

        now = datetime.now(timezone.utc)
        inactive_days = (now - node.last_accessed).total_seconds() / 86400

        if inactive_days > self.inactive_days:
            return LifecycleState.ARCHIVED

        return None
