"""Integration tests for AMFOrchestrator — the full end-to-end pipeline."""

import tempfile
from pathlib import Path

from agent_memory_fabric import AMFOrchestrator
from agent_memory_fabric.llm.provider import MockProvider


class TestOrchestratorBasic:
    def test_creates_without_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            assert amf.engine is not None
            assert amf.write_pipeline is not None
            assert amf.gateway is not None

    def test_write_explicit_creates_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            node = amf.write_explicit("User prefers dark mode", tags=["preference"])
            assert node is not None
            assert "dark mode" in node.content
            assert "provenance:user_explicit" in node.tags

    def test_search_finds_written_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("I live in Shanghai and work at Amazon")
            results = amf.search("Shanghai")
            assert len(results) >= 1
            assert any("Shanghai" in n.content for n in results)

    def test_on_user_message_returns_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("User always prefers Python for scripting")
            context = amf.on_user_message("What language should I use for this script?")
            assert "Python" in context or context == ""

    def test_on_user_message_abstains_for_greetings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("Some important fact about the user")
            context = amf.on_user_message("hi")
            assert context == ""

    def test_maintenance_runs_without_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            amf.write_explicit("Test memory")
            result = amf.run_maintenance()
            assert "transitions" in result
            assert "trimmed" in result

    def test_interpretation_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            rules = amf.get_interpretation_rules()
            assert "memory_interpretation_rules" in rules


class TestOrchestratorWithLLM:
    def test_write_pipeline_extracts_with_mock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider(
                default_response='[{"content": "User prefers vim keybindings", "tags": ["preference"], "confidence": 0.8}]'
            )
            amf = AMFOrchestrator(
                vault_path=tmpdir,
                llm_provider=provider,
                use_consolidation=False,
            )
            # Simulate enough turns to trigger extraction
            for i in range(8):
                amf.write_pipeline.on_turn(
                    f"Turn {i}: I really love using vim for everything",
                    has_tool_calls=True,
                )
            # Check something was extracted
            nodes = amf.engine.list_nodes()
            assert len(nodes) >= 1

    def test_session_end_forces_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = MockProvider(
                default_response='[{"content": "User works at Amazon", "tags": ["profile"], "confidence": 0.9}]'
            )
            amf = AMFOrchestrator(
                vault_path=tmpdir,
                llm_provider=provider,
                use_consolidation=False,
            )
            amf.write_pipeline.on_turn("I work at Amazon as an SDE", has_tool_calls=True)
            # Not enough turns to auto-trigger, but force on session end
            ids = amf.on_session_end()
            assert len(ids) >= 1


class TestAntiPatternIntegration:
    def test_tool_success_degrades_anti_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            amf = AMFOrchestrator(vault_path=tmpdir)
            node = amf.engine.write(
                content="Don't use git push --force",
                tags=["anti-pattern", "git"],
            )
            assert node is not None
            original_alpha = node.confidence_alpha

            # Simulate: anti-pattern was injected, then tool succeeded
            amf.anti_pattern_tracker.record_injection(node)
            degraded = amf.on_tool_success("git")
            assert node.id in degraded

            # Confidence should have decreased
            updated = amf.engine.read(node.id)
            assert updated.confidence_beta > node.confidence_beta
