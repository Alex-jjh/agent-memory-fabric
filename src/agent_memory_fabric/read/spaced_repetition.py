"""Spaced repetition: surface fading memories for reinforcement."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.lifecycle.decay import compute_decay
from agent_memory_fabric.read.scorer import ScoredMemory

DANGER_ZONE_MIN = 0.15
DANGER_ZONE_MAX = 0.35
DANGER_ZONE_MID = (DANGER_ZONE_MIN + DANGER_ZONE_MAX) / 2.0
DANGER_ZONE_HALF_RANGE = (DANGER_ZONE_MAX - DANGER_ZONE_MIN) / 2.0


def compute_review_priority(decay_score: float) -> float:
    """Inverted parabola peaking at the midpoint of the danger zone [0.15, 0.35].

    Memories in this range are fading but not yet lost — ideal for reinforcement.
    Returns 0.0 outside the danger zone, up to 1.0 at the midpoint.
    """
    if decay_score < DANGER_ZONE_MIN or decay_score > DANGER_ZONE_MAX:
        return 0.0
    normalized = (decay_score - DANGER_ZONE_MID) / DANGER_ZONE_HALF_RANGE
    return max(0.0, 1.0 - normalized ** 2)


def select_review_candidates(nodes: list[MemoryNode], limit: int = 5) -> list[MemoryNode]:
    """Select nodes in the danger zone, sorted by review priority."""
    import heapq
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    scored = []
    for node in nodes:
        hours = max(0.0, (now - node.last_accessed).total_seconds() / 3600.0)
        from agent_memory_fabric.lifecycle.decay import ebbinghaus_decay
        decay = ebbinghaus_decay(hours, node.strength)
        priority = compute_review_priority(decay)
        if priority > 0:
            scored.append((priority, id(node), node))

    if not scored:
        return []
    top = heapq.nlargest(limit, scored, key=lambda x: x[0])
    return [node for _, _, node in top]


def blend_with_review(
    primary: list[ScoredMemory],
    review_candidates: list[MemoryNode],
    blend_ratio: float = 0.3,
) -> list[ScoredMemory]:
    """Interleave fading memories into primary results (2 primary : 1 review).

    Total output length equals len(primary). Review candidates replace
    the lowest-scoring primary items up to blend_ratio of total slots.
    """
    if not review_candidates or not primary:
        return primary

    total = len(primary)
    review_slots = min(int(total * blend_ratio), len(review_candidates))
    if review_slots == 0:
        return primary

    primary_items = list(primary[:total - review_slots])
    mean_score = sum(s.total_score for s in primary) / len(primary) if primary else 0.5
    review_items = [
        ScoredMemory(node=n, total_score=mean_score, signal_breakdown={"review": 1.0}, tier="review")
        for n in review_candidates[:review_slots]
    ]

    result: list[ScoredMemory] = []
    p_idx = 0
    r_idx = 0

    while p_idx < len(primary_items) or r_idx < len(review_items):
        for _ in range(2):
            if p_idx < len(primary_items):
                result.append(primary_items[p_idx])
                p_idx += 1
        if r_idx < len(review_items):
            result.append(review_items[r_idx])
            r_idx += 1

    return result[:total]
