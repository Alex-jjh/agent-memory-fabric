"""Integration tests for MemoryEngine — Phase 1."""

from datetime import datetime, timedelta, timezone

import pytest

from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.core.node import LifecycleState


@pytest.fixture
def engine(tmp_path):
    return MemoryEngine(vault_path=tmp_path / "vault")


class TestWriteAndRead:
    def test_write_creates_node(self, engine):
        node = engine.write("User prefers dark mode", name="dark-mode")
        assert node.id is not None
        assert node.name == "dark-mode"
        assert node.state == LifecycleState.ACTIVE

    def test_write_auto_generates_name(self, engine):
        node = engine.write("This is a test memory for things")
        assert node.name == "this-is-a-test-memory"

    def test_read_by_id(self, engine):
        node = engine.write("Hello world", name="hello")
        loaded = engine.read(node.id)
        assert loaded is not None
        assert loaded.content == "Hello world"
        assert loaded.name == "hello"

    def test_read_nonexistent(self, engine):
        assert engine.read("fake-id") is None

    def test_write_with_project(self, engine):
        node = engine.write("AMF architecture decision", name="arch", project="amf")
        assert node.project == "amf"
        loaded = engine.read(node.id)
        assert loaded.project == "amf"

    def test_write_with_tags(self, engine):
        node = engine.write("Tagged memory", name="tagged", tags=["a", "b"])
        loaded = engine.read(node.id)
        assert loaded.tags == ["a", "b"]


class TestListNodes:
    def test_list_all(self, engine):
        engine.write("Node 1", name="n1")
        engine.write("Node 2", name="n2")
        engine.write("Node 3", name="n3")
        nodes = engine.list_nodes()
        assert len(nodes) == 3

    def test_list_by_state(self, engine):
        engine.write("Active", name="active")
        n = engine.write("To archive", name="archive-me")
        engine.transition(n.id, "archived")
        active = engine.list_nodes(state="active")
        assert len(active) == 1
        assert active[0]["name"] == "active"

    def test_list_by_scope(self, engine):
        engine.write("Global", name="g1")
        engine.write("Project", name="p1", project="amf")
        amf = engine.list_nodes(scope="amf")
        assert len(amf) == 1


class TestTransition:
    def test_manual_transition(self, engine):
        node = engine.write("Exploratory idea", name="idea")
        result = engine.transition(node.id, "decided")
        assert result.state == LifecycleState.DECIDED

        loaded = engine.read(node.id)
        assert loaded.state == LifecycleState.DECIDED

    def test_invalid_transition_raises(self, engine):
        node = engine.write("Something", name="exp")
        engine.transition(node.id, "expired")
        with pytest.raises(ValueError):
            engine.transition(node.id, "active")

    def test_transition_nonexistent_raises(self, engine):
        with pytest.raises(ValueError, match="Node not found"):
            engine.transition("fake-id", "archived")


class TestRunTransitions:
    def test_ttl_expiration(self, engine):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        node = engine.write("Meeting at 3pm", name="meeting", ttl=past)

        transitions = engine.run_transitions()
        assert len(transitions) == 1
        assert transitions[0][0] == node.id
        assert transitions[0][2] == LifecycleState.EXPIRED

        loaded = engine.read(node.id)
        assert loaded.state == LifecycleState.EXPIRED

    def test_no_transitions_for_fresh_nodes(self, engine):
        engine.write("Just created", name="fresh")
        transitions = engine.run_transitions()
        assert transitions == []


class TestSearch:
    def test_basic_search(self, engine):
        engine.write("User prefers dark mode for coding", name="dark-mode")
        engine.write("Python is the best language", name="python")

        results = engine.search("dark mode")
        assert len(results) >= 1
        assert results[0].name == "dark-mode"

    def test_search_excludes_expired(self, engine):
        node = engine.write("Old meeting note", name="old-meeting")
        engine.transition(node.id, "expired")

        results = engine.search("meeting")
        assert len(results) == 0

    def test_search_excludes_archived_by_default(self, engine):
        node = engine.write("Archived fact", name="archived-fact")
        engine.transition(node.id, "archived")

        results = engine.search("archived fact")
        assert len(results) == 0

    def test_search_includes_archived_when_requested(self, engine):
        node = engine.write("Archived fact", name="archived-fact")
        engine.transition(node.id, "archived")

        results = engine.search("archived fact", include_archived=True)
        assert len(results) == 1

    def test_search_with_scope_filter(self, engine):
        engine.write("AMF design", name="amf-design", project="amf")
        engine.write("Other project", name="other-design", project="other")

        results = engine.search("design", scope="amf")
        assert len(results) == 1
        assert results[0].project == "amf"


class TestWikilinks:
    def test_wikilinks_create_edges(self, engine):
        engine.write("First memory", name="first")
        engine.write("Second links to [[first]]", name="second")

        all_nodes = engine.sqlite_store.get_all_nodes()
        second_node = next(n for n in all_nodes if n["name"] == "second")
        neighbors = engine.sqlite_store.get_neighbors(second_node["id"])
        first_node = next(n for n in all_nodes if n["name"] == "first")
        assert first_node["id"] in neighbors


class TestReconcile:
    def test_reconcile_on_restart(self, tmp_path):
        vault = tmp_path / "vault"
        engine1 = MemoryEngine(vault_path=vault)
        node = engine1.write("Persistent memory", name="persist")
        engine1.sqlite_store.close()

        engine2 = MemoryEngine(vault_path=vault)
        loaded = engine2.read(node.id)
        assert loaded is not None
        assert loaded.content == "Persistent memory"
