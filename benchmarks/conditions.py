"""Three experimental conditions for Paper 1 ablation.

Control A: Flat Memory (no decay, no lifecycle)
Control B: Continuous Decay (CortexGraph-like power-law, no discrete states)
Treatment: AMF Lifecycle (full discrete state machine)
"""

from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.config import AMFConfig, DecayConfig
from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.llm.provider import LLMProvider, MockProvider


class ExperimentCondition(ABC):
    """Base class for experimental conditions."""

    name: str

    @abstractmethod
    def create_engine(self, vault_path: Path) -> MemoryEngine:
        """Create a configured MemoryEngine for this condition."""
        ...

    @abstractmethod
    def after_session(self, engine: MemoryEngine) -> None:
        """Called after each conversation session is ingested. Run decay/transitions."""
        ...

    def search(self, engine: MemoryEngine, query: str, top_k: int = 5) -> list[MemoryNode]:
        """Retrieve memories for a query under this condition's rules."""
        return engine.search(query, top_k=top_k, touch=False)


class FlatMemoryCondition(ExperimentCondition):
    """Control A: No decay, no lifecycle. All memories equal weight forever.

    - No state transitions
    - No decay scoring
    - All memories are always retrievable regardless of age
    - Simulates a naive append-only memory store
    """

    name = "flat"

    def create_engine(self, vault_path: Path) -> MemoryEngine:
        config = AMFConfig(
            vault_path=vault_path,
            decay=DecayConfig(
                model="exponential",
                half_life_days=99999.0,  # effectively no decay
                forget_threshold=0.0,    # never forget
                promote_threshold=1.0,   # never auto-promote
            ),
        )
        return MemoryEngine(config=config)

    def after_session(self, engine: MemoryEngine) -> None:
        pass  # No transitions, no decay updates


class ContinuousDecayCondition(ExperimentCondition):
    """Control B: CortexGraph-like continuous power-law decay, no discrete states.

    - Decay score decreases over time (power-law model)
    - Memories with lower scores rank lower in retrieval
    - BUT no state transitions: memories never become "invisible"
    - Even very old memories with score ~0.01 are still retrievable (just ranked low)
    """

    name = "continuous_decay"

    def __init__(self, half_life_days: float = 3.0):
        self.half_life_days = half_life_days

    def create_engine(self, vault_path: Path) -> MemoryEngine:
        config = AMFConfig(
            vault_path=vault_path,
            decay=DecayConfig(
                model="power_law",
                half_life_days=self.half_life_days,
                forget_threshold=0.0,    # never auto-archive (no state transitions)
                promote_threshold=1.0,   # never auto-promote
            ),
        )
        return MemoryEngine(config=config)

    def after_session(self, engine: MemoryEngine) -> None:
        # Don't run transitions — continuous decay affects scoring only, not visibility
        pass

    def search(self, engine: MemoryEngine, query: str, top_k: int = 5) -> list[MemoryNode]:
        # Include ALL memories regardless of state (decay only affects ranking)
        return engine.search(query, top_k=top_k, include_archived=True, touch=False)


class LifecycleCondition(ExperimentCondition):
    """Treatment: Full AMF lifecycle with discrete state machine.

    - Decay informs state transitions (but doesn't directly affect retrieval score)
    - State machine: Active → Decided → Archived → Expired
    - Archived nodes EXCLUDED from warm-tier retrieval
    - Expired nodes EXCLUDED from all retrieval
    - Transitions fire after each session
    - This is the hypothesis: discrete states improve precision by removing stale memories
    """

    name = "lifecycle"

    def __init__(self, forget_threshold: float = 0.05, min_inactive_days: int = 30):
        self.forget_threshold = forget_threshold
        self.min_inactive_days = min_inactive_days

    def create_engine(self, vault_path: Path) -> MemoryEngine:
        config = AMFConfig(
            vault_path=vault_path,
            decay=DecayConfig(
                model="ebbinghaus",
                half_life_days=30.0,
                forget_threshold=self.forget_threshold,
                promote_threshold=0.65,
            ),
        )
        return MemoryEngine(config=config)

    def after_session(self, engine: MemoryEngine) -> None:
        engine.run_transitions()

    def search(self, engine: MemoryEngine, query: str, top_k: int = 5) -> list[MemoryNode]:
        # Default: exclude Archived and Expired (the discrete-state advantage)
        return engine.search(query, top_k=top_k, include_archived=False, touch=False)


class SemanticLifecycleCondition(ExperimentCondition):
    """Treatment D: LLM-assisted contradiction detection + lifecycle.

    - After each session, detect contradictions between new and existing memories
    - Only archive CONTRADICTED memories (semantically outdated)
    - Also run time-based transitions as fallback
    - This is the Paper 1 hypothesis: semantic-aware state transitions
      outperform both time-based lifecycle and no lifecycle at all
    """

    name = "semantic_lifecycle"

    def __init__(self, provider: LLMProvider | None = None):
        self._provider = provider

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = self._create_default_provider()
        return self._provider

    def _create_default_provider(self) -> LLMProvider:
        return MockProvider(default_response="NO")

    def create_engine(self, vault_path: Path) -> MemoryEngine:
        config = AMFConfig(
            vault_path=vault_path,
            decay=DecayConfig(
                model="ebbinghaus",
                half_life_days=30.0,
                forget_threshold=0.05,
                promote_threshold=0.65,
            ),
        )
        return MemoryEngine(config=config)

    def after_session(self, engine: MemoryEngine) -> None:
        engine.run_transitions()

    def ingest_with_contradiction_check(
        self, engine: MemoryEngine, content: str
    ) -> list[tuple[str, str]]:
        """Ingest content and archive any contradicted memories."""
        return engine.detect_and_archive_contradictions(content, self.provider)

    def search(self, engine: MemoryEngine, query: str, top_k: int = 5) -> list[MemoryNode]:
        return engine.search(query, top_k=top_k, include_archived=False, touch=False)
