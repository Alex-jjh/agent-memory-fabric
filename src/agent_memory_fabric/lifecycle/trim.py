"""Auto-trim: evict lowest-value memories when corpus exceeds capacity."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.confidence import BetaConfidence
from agent_memory_fabric.lifecycle.protection import is_protected

MEMORY_LIMIT = 10000
TRIM_RATIO = 0.10
TRIM_RECENCY_HALFLIFE_DAYS = 30.0


def recency_sigmoid(age_seconds: float, halflife_seconds: float) -> float:
    """Sigmoid decay: 1.0 at age=0, 0.5 at age=halflife, approaching 0 after."""
    if halflife_seconds <= 0:
        return 0.0
    divisor = halflife_seconds / 4.0
    return 1.0 / (1.0 + math.exp((age_seconds - halflife_seconds) / divisor))


def compute_trim_score(node: MemoryNode, now: datetime | None = None) -> float:
    """Score a node for trim priority. Lower score = more likely to be trimmed.

    Formula: 0.4 * effective_confidence + 0.3 * recency + 0.3 * utility
    """
    if now is None:
        now = datetime.now(timezone.utc)

    conf = BetaConfidence(alpha=node.confidence_alpha, beta_param=node.confidence_beta)
    effective_conf = conf.effective_confidence()

    last_access = node.last_accessed or node.created
    age_secs = max(0.0, (now - last_access).total_seconds())
    halflife_secs = TRIM_RECENCY_HALFLIFE_DAYS * 86400.0
    recency = recency_sigmoid(age_secs, halflife_secs)

    success_count = max(node.confidence_alpha - 1.0, 0.0)
    failure_count = max(node.confidence_beta - 1.0, 0.0)
    total_outcomes = success_count + failure_count
    utility = success_count / total_outcomes if total_outcomes > 0 else 0.0

    return 0.4 * effective_conf + 0.3 * recency + 0.3 * utility


class AutoTrimmer:
    """Evicts lowest-scoring non-protected memories when capacity is exceeded."""

    def __init__(
        self,
        max_count: int = MEMORY_LIMIT,
        trim_ratio: float = TRIM_RATIO,
    ):
        self.max_count = max_count
        self.trim_ratio = trim_ratio

    def needs_trim(self, total_count: int) -> bool:
        return total_count > self.max_count

    def select_for_trim(self, nodes: list[MemoryNode]) -> list[MemoryNode]:
        """Select lowest-scoring non-protected nodes for trimming."""
        trimmable = [n for n in nodes if not is_protected(n)]
        if not trimmable:
            return []

        trim_count = max(1, int(len(nodes) * self.trim_ratio))
        trim_count = min(trim_count, len(trimmable))

        now = datetime.now(timezone.utc)
        scored = [(n, compute_trim_score(n, now)) for n in trimmable]
        scored.sort(key=lambda x: x[1])

        return [n for n, _ in scored[:trim_count]]

    def execute_trim(self, engine, nodes: list[MemoryNode]) -> int:
        """Transition selected nodes to ARCHIVED. Returns count trimmed."""
        count = 0
        for node in nodes:
            try:
                engine.transition(node.id, LifecycleState.ARCHIVED, reason="auto-trim: low value score")
                count += 1
            except ValueError:
                continue
        return count
