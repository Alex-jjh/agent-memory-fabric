"""Tests for LLM Reranker."""

import json
from datetime import datetime, timezone

from agent_memory_fabric.core.node import MemoryNode, MemoryType
from agent_memory_fabric.read.reranker import LLMReranker
from agent_memory_fabric.read.scorer import ScoredMemory


def _sm(node_id, content="test content", score=0.5):
    node = MemoryNode(id=node_id, name=f"node-{node_id}", content=content, type=MemoryType.PROJECT)
    return ScoredMemory(node=node, total_score=score, signal_breakdown={})


class MockLLM:
    def __init__(self, response=""):
        self.response = response

    def complete(self, system, user):
        return self.response


class FailLLM:
    def complete(self, system, user):
        raise RuntimeError("timeout")


class TestLLMReranker:
    def test_successful_rerank(self):
        response = json.dumps({"selected_memories": ["n2", "n1"]})
        reranker = LLMReranker(provider=MockLLM(response), top_k=2)
        candidates = [_sm("n1", score=0.9), _sm("n2", score=0.8), _sm("n3", score=0.7)]
        result = reranker.rerank("test query", candidates)
        assert len(result) == 2
        assert result[0].node.id == "n2"
        assert result[1].node.id == "n1"

    def test_fallback_on_llm_error(self):
        reranker = LLMReranker(provider=FailLLM(), top_k=2)
        candidates = [_sm("n1", score=0.9), _sm("n2", score=0.8), _sm("n3", score=0.7)]
        result = reranker.rerank("test query", candidates)
        assert len(result) == 2
        assert result[0].node.id == "n1"  # fallback to score order

    def test_fallback_on_invalid_json(self):
        reranker = LLMReranker(provider=MockLLM("not json at all"), top_k=2)
        candidates = [_sm("n1", score=0.9), _sm("n2", score=0.8), _sm("n3", score=0.7)]
        result = reranker.rerank("test query", candidates)
        assert len(result) == 2

    def test_fallback_on_empty_selection(self):
        response = json.dumps({"selected_memories": []})
        reranker = LLMReranker(provider=MockLLM(response), top_k=2)
        candidates = [_sm("n1"), _sm("n2"), _sm("n3")]
        result = reranker.rerank("test", candidates)
        assert len(result) == 2

    def test_skips_rerank_when_few_candidates(self):
        reranker = LLMReranker(provider=FailLLM(), top_k=5)
        candidates = [_sm("n1"), _sm("n2")]
        result = reranker.rerank("test", candidates)
        assert len(result) == 2  # returns as-is, no LLM call

    def test_ignores_invalid_ids_in_response(self):
        response = json.dumps({"selected_memories": ["n1", "nonexistent", "n3"]})
        reranker = LLMReranker(provider=MockLLM(response), top_k=3)
        candidates = [_sm("n1"), _sm("n2"), _sm("n3"), _sm("n4")]
        result = reranker.rerank("test", candidates)
        ids = [sm.node.id for sm in result]
        assert "n1" in ids
        assert "n3" in ids
        assert "nonexistent" not in ids

    def test_manifest_format(self):
        reranker = LLMReranker(provider=MockLLM("{}"), top_k=2)
        candidates = [_sm("abc", content="User likes Python programming")]
        manifest = reranker._build_manifest(candidates)
        assert "[abc]" in manifest
        assert "Python" in manifest
        assert "(project)" in manifest
