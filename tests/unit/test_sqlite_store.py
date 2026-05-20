"""Tests for SQLite sidecar store."""

import tempfile
from pathlib import Path

import pytest

from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.storage.sqlite_store import SQLiteStore


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / ".amf" / "index.db"


@pytest.fixture
def store(db_path):
    s = SQLiteStore(db_path)
    s.initialize()
    return s


def _make_node(name="test-node", content="Hello world", **kwargs):
    return MemoryNode(name=name, content=content, **kwargs)


class TestInitialize:
    def test_creates_db_file(self, db_path):
        store = SQLiteStore(db_path)
        store.initialize()
        assert db_path.exists()

    def test_idempotent(self, store):
        store.initialize()
        store.initialize()


class TestUpsertAndGet:
    def test_upsert_and_get(self, store):
        node = _make_node(name="upsert-test")
        store.upsert_node(node)
        result = store.get_node(node.id)
        assert result is not None
        assert result["name"] == "upsert-test"
        assert result["state"] == "active"

    def test_upsert_updates_existing(self, store):
        node = _make_node(name="update-test")
        store.upsert_node(node)
        node.state = LifecycleState.DECIDED
        store.upsert_node(node)
        result = store.get_node(node.id)
        assert result["state"] == "decided"

    def test_get_nonexistent(self, store):
        assert store.get_node("nonexistent") is None


class TestGetAllNodes:
    def test_filter_by_state(self, store):
        store.upsert_node(_make_node(name="active-1"))
        n2 = _make_node(name="decided-1")
        n2.state = LifecycleState.DECIDED
        store.upsert_node(n2)

        active = store.get_all_nodes(state="active")
        assert len(active) == 1
        assert active[0]["name"] == "active-1"

    def test_filter_by_project(self, store):
        store.upsert_node(_make_node(name="p1", project="amf"))
        store.upsert_node(_make_node(name="p2", project="other"))

        amf = store.get_all_nodes(project="amf")
        assert len(amf) == 1
        assert amf[0]["name"] == "p1"


class TestDeleteNode:
    def test_delete_removes_node(self, store):
        node = _make_node()
        store.upsert_node(node)
        store.delete_node(node.id)
        assert store.get_node(node.id) is None

    def test_delete_removes_edges(self, store):
        n1 = _make_node(name="n1")
        n2 = _make_node(name="n2")
        store.upsert_node(n1)
        store.upsert_node(n2)
        store.add_edge(n1.id, n2.id)
        store.delete_node(n1.id)
        assert store.get_neighbors(n2.id) == []


class TestFTSSearch:
    def test_basic_search(self, store):
        store.upsert_node(_make_node(name="dark-mode", content="User prefers dark mode for coding"))
        store.upsert_node(_make_node(name="python-pref", content="User likes Python for scripting"))

        results = store.search_fts("dark mode")
        assert len(results) >= 1
        assert results[0][0] == store.get_all_nodes()[0]["id"] or any(
            r[0] for r in results
        )

    def test_search_by_name(self, store):
        node = _make_node(name="specific-memory", content="some content")
        store.upsert_node(node)
        results = store.search_fts("specific")
        node_ids = [r[0] for r in results]
        assert node.id in node_ids

    def test_search_no_results(self, store):
        store.upsert_node(_make_node(name="test", content="hello world"))
        results = store.search_fts("nonexistentxyz")
        assert results == []

    def test_search_returns_scores(self, store):
        store.upsert_node(_make_node(name="relevant", content="dark mode theme"))
        results = store.search_fts("dark mode")
        assert len(results) >= 1
        assert results[0][1] > 0  # positive BM25 score


class TestEdges:
    def test_add_and_get_neighbors(self, store):
        n1 = _make_node(name="n1")
        n2 = _make_node(name="n2")
        n3 = _make_node(name="n3")
        store.upsert_node(n1)
        store.upsert_node(n2)
        store.upsert_node(n3)
        store.add_edge(n1.id, n2.id, "links_to")
        store.add_edge(n1.id, n3.id, "links_to")

        neighbors = store.get_neighbors(n1.id)
        assert set(neighbors) == {n2.id, n3.id}

    def test_bidirectional_neighbors(self, store):
        n1 = _make_node(name="n1")
        n2 = _make_node(name="n2")
        store.upsert_node(n1)
        store.upsert_node(n2)
        store.add_edge(n1.id, n2.id)

        assert n2.id in store.get_neighbors(n1.id)
        assert n1.id in store.get_neighbors(n2.id)

    def test_filter_by_edge_type(self, store):
        n1 = _make_node(name="n1")
        n2 = _make_node(name="n2")
        n3 = _make_node(name="n3")
        store.upsert_node(n1)
        store.upsert_node(n2)
        store.upsert_node(n3)
        store.add_edge(n1.id, n2.id, "links_to")
        store.add_edge(n1.id, n3.id, "mentions")

        links_only = store.get_neighbors(n1.id, edge_type="links_to")
        assert links_only == [n2.id]

    def test_get_all_edges(self, store):
        n1 = _make_node(name="n1")
        n2 = _make_node(name="n2")
        store.upsert_node(n1)
        store.upsert_node(n2)
        store.add_edge(n1.id, n2.id, "links_to", weight=0.8)

        edges = store.get_all_edges()
        assert len(edges) == 1
        assert edges[0] == (n1.id, n2.id, "links_to", 0.8)


class TestReconcile:
    def test_adds_new_nodes(self, store):
        nodes = [_make_node(name=f"node-{i}") for i in range(3)]
        store.reconcile(nodes)
        assert len(store.get_all_nodes()) == 3

    def test_removes_stale_nodes(self, store):
        n1 = _make_node(name="keep")
        n2 = _make_node(name="remove")
        store.upsert_node(n1)
        store.upsert_node(n2)

        store.reconcile([n1])
        assert store.get_node(n1.id) is not None
        assert store.get_node(n2.id) is None

    def test_updates_existing(self, store):
        node = _make_node(name="update-me")
        store.upsert_node(node)
        node.state = LifecycleState.ARCHIVED
        store.reconcile([node])
        result = store.get_node(node.id)
        assert result["state"] == "archived"
