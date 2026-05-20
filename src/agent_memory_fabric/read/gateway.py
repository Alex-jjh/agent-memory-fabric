"""Proactive Retrieval Gateway — decides what to inject before agent sees the message."""

from __future__ import annotations

from agent_memory_fabric.core.config import RetrieverConfig
from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.read.scorer import ScoredMemory


class ProactiveGateway:
    """Fires on message arrival, selects memories for injection within <100ms budget.

    Pipeline:
    1. Scope inference (which project context?)
    2. Intent classification (what kind of memory is needed?)
    3. Candidate selection (lifecycle-filtered, scope-filtered)
    4. Multi-signal scoring
    5. Tiered budget allocation (hot: ~1300tok, warm: ~2000tok)
    6. Format for injection
    """

    def __init__(self, config: RetrieverConfig):
        self.config = config

    def inject(self, message: str, scope: str | None = None) -> list[ScoredMemory]:
        """Select and return memories to inject for an incoming message."""
        raise NotImplementedError("Phase 3: proactive gateway")

    def infer_scope(self, message: str) -> str | None:
        """Infer project scope from message content."""
        raise NotImplementedError("Phase 3: scope inference")
