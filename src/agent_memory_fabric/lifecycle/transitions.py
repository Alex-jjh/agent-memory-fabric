"""Transition predicates — conditions that trigger state changes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.decay import compute_decay
from agent_memory_fabric.lifecycle.protection import is_protected


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
        if is_protected(node):
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
        if is_protected(node):
            return None

        now = datetime.now(timezone.utc)
        inactive_days = (now - node.last_accessed).total_seconds() / 86400

        if inactive_days > self.inactive_days:
            return LifecycleState.ARCHIVED

        return None


class PromotionPredicate:
    """Promote Active nodes to Decided when they demonstrate sustained value.

    Two paths to promotion:
    1. High composite score (decay-resistant, frequently accessed) AND minimum age met
    2. High access count within a recent time window
    """

    def __init__(
        self,
        score_threshold: float = 0.65,
        access_threshold: int = 5,
        window_days: int = 14,
        min_age_days: float = 1.0,
    ):
        self.score_threshold = score_threshold
        self.access_threshold = access_threshold
        self.window_days = window_days
        self.min_age_days = min_age_days

    def evaluate(self, node: MemoryNode) -> LifecycleState | None:
        if node.state != LifecycleState.ACTIVE:
            return None

        now = datetime.now(timezone.utc)
        age_days = (now - node.created).total_seconds() / 86400

        if age_days < self.min_age_days:
            return None

        score = compute_decay(node.last_accessed, strength=node.strength)
        if score >= self.score_threshold and node.access_count >= 2:
            return LifecycleState.DECIDED

        if node.access_count >= self.access_threshold and age_days <= self.window_days:
            return LifecycleState.DECIDED

        return None
