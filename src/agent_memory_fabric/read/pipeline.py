"""Multi-pipeline retrieval with token budgets."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_memory_fabric.core.node import MemoryType
from agent_memory_fabric.read.scorer import ScoredMemory


@dataclass
class PipelineConfig:
    name: str
    budget_ratio: float
    memory_types: list[MemoryType]
    confidence_floor: float = 0.3
    relevance_threshold: float = 0.15


DEFAULT_PIPELINES = [
    PipelineConfig(name="profile", budget_ratio=0.20, memory_types=[MemoryType.USER], confidence_floor=0.0),
    PipelineConfig(name="feedback", budget_ratio=0.30, memory_types=[MemoryType.FEEDBACK], confidence_floor=0.3),
    PipelineConfig(name="project", budget_ratio=0.30, memory_types=[MemoryType.PROJECT, MemoryType.REFERENCE]),
    PipelineConfig(name="domain", budget_ratio=0.10, memory_types=[MemoryType.ENTITY], confidence_floor=0.0),
    PipelineConfig(name="carryover", budget_ratio=0.10, memory_types=[], confidence_floor=0.5),
]


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


class PipelineRetriever:
    """Allocates scored memories across pipelines with per-pipeline token budgets."""

    def __init__(
        self,
        pipelines: list[PipelineConfig] | None = None,
        total_budget_tokens: int = 4000,
    ):
        self.pipelines = pipelines or DEFAULT_PIPELINES
        self.total_budget_tokens = total_budget_tokens

    def allocate(self, scored_memories: list[ScoredMemory]) -> list[ScoredMemory]:
        """Select memories respecting per-pipeline budgets. Returns deduplicated selection."""
        selected_ids: set[str] = set()
        selected: list[ScoredMemory] = []

        for pipeline in self.pipelines:
            budget = int(self.total_budget_tokens * pipeline.budget_ratio)
            candidates = self._filter_for_pipeline(scored_memories, pipeline, selected_ids)
            pipeline_selected = self._greedy_fill(candidates, budget, pipeline)

            for sm in pipeline_selected:
                selected_ids.add(sm.node.id)
                selected.append(sm)

        return selected

    def _filter_for_pipeline(
        self,
        memories: list[ScoredMemory],
        pipeline: PipelineConfig,
        already_selected: set[str],
    ) -> list[ScoredMemory]:
        """Filter memories matching this pipeline's criteria."""
        from agent_memory_fabric.lifecycle.confidence import BetaConfidence

        result = []
        for sm in memories:
            if sm.node.id in already_selected:
                continue
            if pipeline.memory_types and sm.node.type not in pipeline.memory_types:
                continue
            if sm.total_score < pipeline.relevance_threshold:
                continue
            conf = BetaConfidence(
                alpha=sm.node.confidence_alpha,
                beta_param=sm.node.confidence_beta,
                recent_outcomes=list(sm.node.recent_outcomes),
                is_anti_pattern=sm.node.is_anti_pattern,
            ).effective_confidence()
            if conf < pipeline.confidence_floor:
                continue
            result.append(sm)
        return result

    def _greedy_fill(
        self,
        candidates: list[ScoredMemory],
        budget_tokens: int,
        pipeline: PipelineConfig,
    ) -> list[ScoredMemory]:
        """Greedily select highest-scoring memories within token budget."""
        sorted_candidates = sorted(candidates, key=lambda s: s.total_score, reverse=True)
        selected: list[ScoredMemory] = []
        tokens_used = 0

        for sm in sorted_candidates:
            cost = _estimate_tokens(sm.node.content)
            if tokens_used + cost > budget_tokens:
                continue
            selected.append(sm)
            tokens_used += cost

        return selected
