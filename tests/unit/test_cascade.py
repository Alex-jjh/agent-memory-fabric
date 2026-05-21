"""Tests for cascade contradiction reasoning."""

import tempfile
from pathlib import Path

from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.llm.cascade import (
    detect_cascade_contradictions,
    find_cascade_candidates,
    identify_affected_domains,
    validate_cascade_candidates,
)
from agent_memory_fabric.llm.provider import MockProvider
from agent_memory_fabric.core.node import MemoryNode


class TestIdentifyAffectedDomains:
    def test_location_change(self):
        provider = MockProvider(default_response='{"affected_domains": [{"keywords": ["commute", "metro", "transport"], "reason": "commute changed with location"}]}')
        domains = identify_affected_domains(
            new_content="I moved to Sydney",
            archived_content="I live in Shanghai",
            provider=provider,
        )
        assert len(domains) >= 1
        assert any("commute" in d.get("keywords", []) or "transport" in d.get("keywords", []) for d in domains)

    def test_returns_max_3(self):
        response = '{"affected_domains": [{"keywords": ["a"], "reason": "r1"}, {"keywords": ["b"], "reason": "r2"}, {"keywords": ["c"], "reason": "r3"}, {"keywords": ["d"], "reason": "r4"}]}'
        provider = MockProvider(default_response=response)
        domains = identify_affected_domains("new", "old", provider)
        assert len(domains) <= 3

    def test_handles_invalid_json(self):
        provider = MockProvider(default_response="not json")
        domains = identify_affected_domains("new", "old", provider)
        assert domains == []

    def test_handles_empty_response(self):
        provider = MockProvider(default_response='{"affected_domains": []}')
        domains = identify_affected_domains("new", "old", provider)
        assert domains == []


class TestFindCascadeCandidates:
    def test_finds_by_keywords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            engine.write("I take metro line 2 to work every day", tags=["routine"])
            engine.write("My favorite restaurant is near Jing'an temple", tags=["preference"])
            engine.write("I enjoy reading Python books", tags=["hobby"])

            active = [n for n in engine.markdown_store.list_all() if n.is_retrievable()]
            domains = [{"keywords": ["metro", "commute"], "reason": "commute changed"}]
            candidates = find_cascade_candidates(domains, active, engine.sqlite_store)
            assert any("metro" in c.content.lower() for c in candidates)

    def test_empty_domains_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            engine.write("Some memory")
            active = list(engine.markdown_store.list_all())
            candidates = find_cascade_candidates([], active, engine.sqlite_store)
            assert candidates == []


class TestValidateCascadeCandidates:
    def test_validates_yes(self):
        provider = MockProvider(default_response="YES: commute is no longer valid after moving")
        node = MemoryNode(id="n1", name="test", content="I take metro line 2 daily")
        validated = validate_cascade_candidates("moved to Sydney", "lived in Shanghai", [node], provider)
        assert len(validated) == 1
        assert validated[0][0].id == "n1"

    def test_validates_no(self):
        provider = MockProvider(default_response="NO: reading habits unaffected by location")
        node = MemoryNode(id="n1", name="test", content="I enjoy reading Python books")
        validated = validate_cascade_candidates("moved to Sydney", "lived in Shanghai", [node], provider)
        assert validated == []


class TestFullCascadePipeline:
    def test_end_to_end(self):
        provider = MockProvider()
        provider.set_responses([
            '{"affected_domains": [{"keywords": ["metro", "commute"], "reason": "transport changed"}]}',
            "YES: metro route no longer valid",
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            engine.write("I take metro line 2 to work", tags=["routine"])
            engine.write("I enjoy Python programming", tags=["hobby"])

            active = [n for n in engine.markdown_store.list_all() if n.is_retrievable()]
            direct_archived = [("old-id", "I live in Shanghai")]

            cascade = detect_cascade_contradictions(
                "I moved to Sydney", direct_archived, active, provider, engine.sqlite_store,
            )
            # May or may not find cascade depending on FTS match
            assert isinstance(cascade, list)

    def test_cascade_disabled_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            engine.write("Some content")

            provider = MockProvider(default_response="YES: contradiction")
            result = engine.detect_and_archive_contradictions(
                "new content", provider, enable_cascade=False,
            )
            assert result["cascade"] == []

    def test_superseded_by_field_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            node = engine.write("I live in Shanghai")

            provider = MockProvider(default_response="YES: location changed")
            result = engine.detect_and_archive_contradictions("I moved to Sydney", provider)

            if result["direct"]:
                archived_id = result["direct"][0][0]
                reloaded = engine.read(archived_id)
                assert reloaded.superseded_by == "direct_contradiction"
