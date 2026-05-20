"""Tests for multi-pipeline retrieval."""

from datetime import datetime, timezone

from agent_memory_fabric.core.node import MemoryNode, MemoryType
from agent_memory_fabric.read.pipeline import PipelineConfig, PipelineRetriever
from agent_memory_fabric.read.scorer import ScoredMemory


def _sm(content="x" * 40, mem_type=MemoryType.PROJECT, score=0.5, node_id="n1", alpha=5.0, beta=1.0):
    node = MemoryNode(
        id=node_id, name="test", content=content,
        type=mem_type, confidence_alpha=alpha, confidence_beta=beta,
    )
    return ScoredMemory(node=node, total_score=score, signal_breakdown={})


class TestPipelineRetriever:
    def test_allocates_by_type(self):
        pipelines = [
            PipelineConfig(name="user", budget_ratio=0.5, memory_types=[MemoryType.USER]),
            PipelineConfig(name="project", budget_ratio=0.5, memory_types=[MemoryType.PROJECT]),
        ]
        retriever = PipelineRetriever(pipelines=pipelines, total_budget_tokens=400)
        memories = [
            _sm(node_id="u1", mem_type=MemoryType.USER, score=0.9),
            _sm(node_id="p1", mem_type=MemoryType.PROJECT, score=0.8),
            _sm(node_id="p2", mem_type=MemoryType.PROJECT, score=0.7),
        ]
        result = retriever.allocate(memories)
        result_ids = {sm.node.id for sm in result}
        assert "u1" in result_ids
        assert "p1" in result_ids

    def test_respects_budget(self):
        pipelines = [
            PipelineConfig(name="all", budget_ratio=1.0, memory_types=[MemoryType.PROJECT]),
        ]
        retriever = PipelineRetriever(pipelines=pipelines, total_budget_tokens=20)
        memories = [
            _sm(node_id=f"n{i}", content="x" * 100, score=0.5 + i * 0.01)
            for i in range(10)
        ]
        result = retriever.allocate(memories)
        assert len(result) < 10

    def test_filters_by_confidence_floor(self):
        pipelines = [
            PipelineConfig(name="strict", budget_ratio=1.0, memory_types=[MemoryType.PROJECT], confidence_floor=0.7),
        ]
        retriever = PipelineRetriever(pipelines=pipelines, total_budget_tokens=4000)
        memories = [
            _sm(node_id="high", alpha=8.0, beta=2.0, score=0.9),
            _sm(node_id="low", alpha=1.0, beta=9.0, score=0.9),
        ]
        result = retriever.allocate(memories)
        result_ids = {sm.node.id for sm in result}
        assert "high" in result_ids
        assert "low" not in result_ids

    def test_filters_by_relevance_threshold(self):
        pipelines = [
            PipelineConfig(name="p", budget_ratio=1.0, memory_types=[MemoryType.PROJECT], relevance_threshold=0.5),
        ]
        retriever = PipelineRetriever(pipelines=pipelines, total_budget_tokens=4000)
        memories = [
            _sm(node_id="relevant", score=0.8),
            _sm(node_id="irrelevant", score=0.2),
        ]
        result = retriever.allocate(memories)
        result_ids = {sm.node.id for sm in result}
        assert "relevant" in result_ids
        assert "irrelevant" not in result_ids

    def test_no_duplicates_across_pipelines(self):
        pipelines = [
            PipelineConfig(name="a", budget_ratio=0.5, memory_types=[MemoryType.PROJECT]),
            PipelineConfig(name="b", budget_ratio=0.5, memory_types=[MemoryType.PROJECT]),
        ]
        retriever = PipelineRetriever(pipelines=pipelines, total_budget_tokens=4000)
        memories = [_sm(node_id="shared", score=0.9)]
        result = retriever.allocate(memories)
        assert len(result) == 1

    def test_empty_input(self):
        retriever = PipelineRetriever()
        assert retriever.allocate([]) == []
