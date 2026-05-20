"""Multi-signal scorer for memory retrieval ranking.

- RRF adapted from Hindsight (MIT License, Vectorize AI 2025)
- BM25 sigmoid normalization adapted from Mem0 (Apache 2.0, Taranjeet Singh 2023)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_memory_fabric.core.config import ScorerWeights
from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.decay import compute_decay


@dataclass
class ScoredMemory:
    node: MemoryNode
    total_score: float
    signal_breakdown: dict[str, float] = field(default_factory=dict)
    tier: str = "warm"


# Adapted from Mem0 (Apache 2.0) — BM25 sigmoid normalization
def normalize_bm25(raw_score: float, midpoint: float = 8.0, steepness: float = 0.6) -> float:
    """Normalize raw BM25 score to [0, 1] via logistic sigmoid."""
    return 1.0 / (1.0 + math.exp(-steepness * (raw_score - midpoint)))


# Adapted from Hindsight (MIT) — Reciprocal Rank Fusion
def reciprocal_rank_fusion(
    result_lists: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge multiple ranked result lists using RRF.

    Args:
        result_lists: Each list contains (node_id, score) pairs, sorted best-first.
        k: RRF constant (default 60, from Cormack et al. 2009).

    Returns:
        Merged (node_id, rrf_score) pairs sorted by descending RRF score.
    """
    rrf_scores: dict[str, float] = {}

    for results in result_lists:
        for rank, (node_id, _score) in enumerate(results, start=1):
            rrf_scores[node_id] = rrf_scores.get(node_id, 0.0) + 1.0 / (k + rank)

    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


def normalize_frequency(access_count: int) -> float:
    """Log-normalize access count to [0, 1] range."""
    if access_count <= 0:
        return 0.0
    return min(1.0, math.log(1 + access_count) / math.log(100))


class MultiSignalScorer:
    """Ranks memories using weighted signals.

    V1 Signals (Phase 2):
    - bm25: Keyword match relevance (FTS5 score, sigmoid normalized)
    - recency: Temporal decay score
    - frequency: Normalized access count

    V2 Signals (Phase 3):
    - semantic: Cosine similarity of embeddings
    - graph_proximity: PPR score from query entities
    - intent: Match between query intent and node type
    """

    def __init__(self, weights: ScorerWeights | None = None):
        self.weights = weights or ScorerWeights()

    def score(
        self,
        candidates: list[MemoryNode],
        fts_scores: dict[str, float] | None = None,
        state_filter: set[LifecycleState] | None = None,
    ) -> list[ScoredMemory]:
        """Score and rank candidate memories.

        Args:
            candidates: Nodes to score.
            fts_scores: Optional dict of node_id -> raw BM25 score from FTS5.
            state_filter: Only include nodes in these states (default: Active + Decided).

        Returns:
            Scored memories sorted by total_score descending, with tier assignment.
        """
        if state_filter is None:
            state_filter = {LifecycleState.ACTIVE, LifecycleState.DECIDED}

        fts_scores = fts_scores or {}
        scored: list[ScoredMemory] = []

        for node in candidates:
            if node.state not in state_filter:
                continue

            bm25_raw = fts_scores.get(node.id, 0.0)
            bm25_norm = normalize_bm25(bm25_raw) if bm25_raw > 0 else 0.0

            recency = compute_decay(node.last_accessed)

            frequency = normalize_frequency(node.access_count)

            signals = {
                "bm25": bm25_norm,
                "recency": recency,
                "frequency": frequency,
            }

            total = (
                self.weights.semantic * bm25_norm
                + self.weights.recency * recency
                + self.weights.frequency * frequency
            )

            scored.append(ScoredMemory(
                node=node,
                total_score=total,
                signal_breakdown=signals,
            ))

        scored.sort(key=lambda s: s.total_score, reverse=True)
        self._assign_tiers(scored)
        return scored

    def _assign_tiers(self, scored: list[ScoredMemory]) -> None:
        """Assign hot/warm/cold tiers based on score rank position."""
        n = len(scored)
        for i, s in enumerate(scored):
            if i < n * 0.3:
                s.tier = "hot"
            elif i < n * 0.7:
                s.tier = "warm"
            else:
                s.tier = "cold"
