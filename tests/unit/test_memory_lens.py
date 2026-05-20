"""Tests for MemoryLens evaluation metrics."""

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.eval.memory_lens import MemoryLens, MemoryLensReport


def _node(content, node_id="n1"):
    return MemoryNode(id=node_id, name=f"node-{node_id}", content=content)


class TestCompressionRate:
    def test_basic_compression(self):
        lens = MemoryLens()
        nodes = [_node("User lives in Shanghai")]
        report = lens.evaluate(nodes, source_tokens=100)
        assert 0 < report.compression_rate < 1

    def test_no_source_tokens(self):
        lens = MemoryLens()
        nodes = [_node("fact")]
        report = lens.evaluate(nodes, source_tokens=None)
        assert report.compression_rate == 0.0

    def test_zero_source_tokens(self):
        lens = MemoryLens()
        nodes = [_node("fact")]
        report = lens.evaluate(nodes, source_tokens=0)
        assert report.compression_rate == 0.0


class TestRedundancyRate:
    def test_no_redundancy(self):
        lens = MemoryLens()
        nodes = [
            _node("User lives in Shanghai", "n1"),
            _node("Favorite language is Python", "n2"),
            _node("Works at Amazon as SDE", "n3"),
        ]
        report = lens.evaluate(nodes)
        assert report.redundancy_rate == 0.0

    def test_high_redundancy(self):
        lens = MemoryLens()
        nodes = [
            _node("User lives in Shanghai and works there", "n1"),
            _node("User lives in Shanghai and works there daily", "n2"),
        ]
        report = lens.evaluate(nodes)
        assert report.redundancy_rate > 0.0

    def test_single_node(self):
        lens = MemoryLens()
        report = lens.evaluate([_node("single")])
        assert report.redundancy_rate == 0.0


class TestWithMockLLM:
    def test_faithfulness_with_mock(self):
        class MockLLM:
            def complete(self, system, user):
                return '{"faithful": true, "reason": "grounded"}'

        lens = MemoryLens(llm_provider=MockLLM())
        nodes = [_node("User lives in Shanghai", "n1")]
        report = lens.evaluate(nodes, source_text="I live in Shanghai and work at Amazon")
        assert report.faithfulness == 1.0

    def test_conflict_rate_with_mock(self):
        class MockLLM:
            def complete(self, system, user):
                return '{"conflict": false, "reason": "no contradiction"}'

        lens = MemoryLens(llm_provider=MockLLM())
        nodes = [_node("fact a", "n1"), _node("fact b", "n2"), _node("fact c", "n3")]
        report = lens.evaluate(nodes)
        assert report.conflict_rate == 0.0

    def test_report_structure(self):
        lens = MemoryLens()
        nodes = [_node("test", "n1")]
        report = lens.evaluate(nodes)
        assert isinstance(report, MemoryLensReport)
        assert report.sample_size == 1
