"""Tests for MCP server recall tool."""

import tempfile

from agent_memory_fabric import AMFOrchestrator
from agent_memory_fabric.mcp_server.server import AMFMCPServer


class TestMCPRecall:
    def test_recall_returns_formatted_dicts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("User prefers Python for all scripting tasks")
            server = AMFMCPServer(orchestrator=amf)
            results = server.amf_recall("Python")
            assert len(results) >= 1
            assert "content" in results[0]
            assert "confidence" in results[0]
            assert "Python" in results[0]["content"]

    def test_recall_empty_corpus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            server = AMFMCPServer(orchestrator=amf)
            results = server.amf_recall("anything")
            assert results == []

    def test_write_via_mcp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            server = AMFMCPServer(orchestrator=amf)
            result = server.amf_write("Important fact to remember", tags=["project"])
            assert result["status"] == "created"
            assert "id" in result

    def test_status_returns_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("Fact one")
            amf.write_explicit("Fact two")
            server = AMFMCPServer(orchestrator=amf)
            status = server.amf_status()
            assert status["active"] == 2
            assert status["total_searchable"] == 2

    def test_transition_via_mcp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            node = amf.write_explicit("Memory to archive")
            server = AMFMCPServer(orchestrator=amf)
            result = server.amf_transition(node.id, "archived", reason="no longer needed")
            assert result["status"] == "transitioned"
            assert result["new_state"] == "archived"

    def test_transition_invalid_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            server = AMFMCPServer(orchestrator=amf)
            result = server.amf_transition("nonexistent-id", "archived")
            assert result["status"] == "error"
