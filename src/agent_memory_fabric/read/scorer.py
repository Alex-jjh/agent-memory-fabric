"""Multi-signal scorer for memory retrieval ranking."""

from __future__ import annotations

from dataclasses import dataclass

from agent_memory_fabric.core.config import ScorerWeights
from agent_memory_fabric.core.node import MemoryNode


@dataclass
class ScoredMemory:
    node: MemoryNode
    total_score: float
    signal_breakdown: dict[str, float]
    tier: str  # "hot" | "warm" | "cold"


class MultiSignalScorer:
    """Ranks memories using 6 weighted signals.

    Signals:
    - semantic: cosine similarity of query embedding vs node embedding
    - graph_proximity: shortest path / PPR score to query entities
    - recency: temporal decay score (from lifecycle.decay)
    - frequency: normalized access_count
    - intent: match between query intent and node type/tags
    - hierarchy: boost for nodes in the inferred project scope
    """

    def __init__(self, weights: ScorerWeights):
        self.weights = weights

    def score(
        self,
        query: str,
        candidates: list[MemoryNode],
        query_embedding: list[float] | None = None,
        query_project: str | None = None,
    ) -> list[ScoredMemory]:
        """Score and rank candidate memories for a query."""
        raise NotImplementedError("Phase 3: multi-signal scoring")
