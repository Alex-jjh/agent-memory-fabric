"""Tests for Consolidator."""

import json

from agent_memory_fabric.write.consolidator import (
    ConsolidationDecision,
    ConsolidationResult,
    Consolidator,
)


class MockLLM:
    def __init__(self, response: str = ""):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


class FailLLM:
    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("API timeout")


class TestConsolidatorNoStore:
    def test_add_when_no_store(self):
        llm = MockLLM()
        consolidator = Consolidator(llm_provider=llm, sqlite_store=None)
        result = consolidator.consolidate_one("User lives in Shanghai")
        assert result.decision == ConsolidationDecision.ADD
        assert "no similar" in result.reason

    def test_batch_processes_all(self):
        llm = MockLLM()
        consolidator = Consolidator(llm_provider=llm, sqlite_store=None)
        results = consolidator.consolidate_batch(["fact 1", "fact 2", "fact 3"])
        assert len(results) == 3
        assert all(r.decision == ConsolidationDecision.ADD for r in results)


class TestConsolidatorWithLLM:
    def test_add_decision(self):
        response = json.dumps({
            "decision": "add",
            "target_id": None,
            "merged_content": None,
            "reason": "new information not in existing memories",
        })
        llm = MockLLM(response=response)

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("existing-1", 5.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "Existing memory about something else"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=llm, sqlite_store=FakeStore())
        result = consolidator.consolidate_one("User prefers dark mode")
        assert result.decision == ConsolidationDecision.ADD

    def test_update_decision(self):
        response = json.dumps({
            "decision": "update",
            "target_id": "existing-1",
            "merged_content": "User lives in Sydney (moved from Shanghai in May 2026)",
            "reason": "new location supersedes old",
        })
        llm = MockLLM(response=response)

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("existing-1", 8.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "User lives in Shanghai"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=llm, sqlite_store=FakeStore())
        result = consolidator.consolidate_one("User moved to Sydney")
        assert result.decision == ConsolidationDecision.UPDATE
        assert result.target_node_id == "existing-1"
        assert "Sydney" in result.content

    def test_skip_decision(self):
        response = json.dumps({
            "decision": "skip",
            "target_id": None,
            "merged_content": None,
            "reason": "duplicate of existing memory",
        })
        llm = MockLLM(response=response)

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("existing-1", 10.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "User lives in Shanghai"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=llm, sqlite_store=FakeStore())
        result = consolidator.consolidate_one("User lives in Shanghai")
        assert result.decision == ConsolidationDecision.SKIP


class TestFallbackToAdd:
    def test_fallback_on_llm_error(self):
        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("existing-1", 5.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "something"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=FailLLM(), sqlite_store=FakeStore())
        result = consolidator.consolidate_one("new memory content here")
        assert result.decision == ConsolidationDecision.ADD
        assert "fallback" in result.reason

    def test_fallback_on_invalid_json(self):
        llm = MockLLM(response="I don't know what to do")

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("e1", 5.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "existing"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=llm, sqlite_store=FakeStore())
        result = consolidator.consolidate_one("test")
        assert result.decision == ConsolidationDecision.ADD
        assert "fallback" in result.reason

    def test_fallback_on_unknown_decision(self):
        response = json.dumps({"decision": "merge", "reason": "typo"})
        llm = MockLLM(response=response)

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("e1", 5.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "existing"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(llm_provider=llm, sqlite_store=FakeStore())
        result = consolidator.consolidate_one("test")
        assert result.decision == ConsolidationDecision.ADD


class TestBatchProcessing:
    def test_batch_size_respected(self):
        call_count = [0]

        class CountingLLM:
            def complete(self, system, user):
                call_count[0] += 1
                return json.dumps({"decision": "add", "reason": "new"})

        class FakeStore:
            def search_fts(self, query, limit=2):
                return [("e1", 5.0)]
            def get_node(self, node_id):
                return {"id": node_id, "content": "existing"}
            def search_vector(self, embedding, limit=2):
                return []

        consolidator = Consolidator(
            llm_provider=CountingLLM(),
            sqlite_store=FakeStore(),
            batch_size=2,
        )
        results = consolidator.consolidate_batch(["a", "b", "c", "d", "e"])
        assert len(results) == 5
        assert call_count[0] == 5
