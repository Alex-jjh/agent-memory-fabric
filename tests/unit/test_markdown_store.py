"""Tests for Markdown storage."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType
from agent_memory_fabric.storage.markdown import MarkdownStore, extract_wikilinks


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault"


@pytest.fixture
def store(vault):
    return MarkdownStore(vault)


def _make_node(name="test-node", content="Hello world", project=None, **kwargs):
    return MemoryNode(name=name, content=content, project=project, **kwargs)


class TestExtractWikilinks:
    def test_single_link(self):
        assert extract_wikilinks("See [[other-note]] for details") == ["other-note"]

    def test_multiple_links(self):
        result = extract_wikilinks("Link to [[a]] and [[b]] and [[c]]")
        assert result == ["a", "b", "c"]

    def test_no_links(self):
        assert extract_wikilinks("No links here") == []

    def test_nested_brackets_ignored(self):
        assert extract_wikilinks("[[valid]] and [not a link]") == ["valid"]


class TestMarkdownStoreWrite:
    def test_write_creates_file(self, store, vault):
        node = _make_node()
        path = store.write(node)
        assert path.exists()
        assert path.suffix == ".md"

    def test_write_global_scope(self, store, vault):
        node = _make_node(name="my-memory")
        path = store.write(node)
        assert "_global" in str(path)

    def test_write_project_scope(self, store, vault):
        node = _make_node(name="my-memory", project="amf")
        path = store.write(node)
        assert "projects/amf" in str(path)

    def test_write_creates_parent_dirs(self, store, vault):
        node = _make_node(project="deep/nested")
        path = store.write(node)
        assert path.exists()


class TestMarkdownStoreRoundTrip:
    def test_basic_roundtrip(self, store):
        original = _make_node(
            name="roundtrip-test",
            content="This is the content body.",
            tags=["tag1", "tag2"],
        )
        store.write(original)
        loaded = store.read(original.id)

        assert loaded is not None
        assert loaded.id == original.id
        assert loaded.name == original.name
        assert loaded.content == original.content
        assert loaded.state == original.state
        assert loaded.tags == original.tags

    def test_roundtrip_preserves_all_fields(self, store):
        now = datetime.now(timezone.utc)
        original = MemoryNode(
            name="full-fields",
            content="Content here",
            state=LifecycleState.DECIDED,
            type=MemoryType.FEEDBACK,
            project="my-project",
            created=now,
            modified=now,
            last_accessed=now,
            access_count=5,
            decay_score=0.75,
            strength=1.5,
            ttl=now + timedelta(days=7),
            tags=["a", "b"],
            links=["link-1", "link-2"],
        )
        store.write(original)
        loaded = store.read(original.id)

        assert loaded.state == LifecycleState.DECIDED
        assert loaded.type == MemoryType.FEEDBACK
        assert loaded.project == "my-project"
        assert loaded.access_count == 5
        assert loaded.decay_score == 0.75
        assert loaded.strength == 1.5
        assert loaded.ttl is not None
        assert loaded.links == ["link-1", "link-2"]

    def test_roundtrip_with_unicode_content(self, store):
        original = _make_node(name="unicode", content="中文内容 + émojis 🎉")
        store.write(original)
        loaded = store.read(original.id)
        assert loaded.content == "中文内容 + émojis 🎉"

    def test_roundtrip_with_multiline_content(self, store):
        content = "Line 1\n\nLine 2\n\n## Heading\n\n- bullet\n- item"
        original = _make_node(name="multiline", content=content)
        store.write(original)
        loaded = store.read(original.id)
        assert loaded.content == content


class TestMarkdownStoreDelete:
    def test_delete_existing(self, store):
        node = _make_node()
        store.write(node)
        assert store.delete(node.id) is True
        assert store.read(node.id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete("nonexistent-id") is False


class TestMarkdownStoreListAll:
    def test_list_empty_vault(self, store):
        assert store.list_all() == []

    def test_list_multiple_nodes(self, store):
        for i in range(5):
            store.write(_make_node(name=f"node-{i}"))
        nodes = store.list_all()
        assert len(nodes) == 5

    def test_list_filtered_by_scope(self, store):
        store.write(_make_node(name="global-1"))
        store.write(_make_node(name="proj-1", project="amf"))
        store.write(_make_node(name="proj-2", project="amf"))
        store.write(_make_node(name="other-1", project="other"))

        amf_nodes = store.list_all(scope="amf")
        assert len(amf_nodes) == 2
        assert all(n.project == "amf" for n in amf_nodes)


class TestMarkdownStoreOverwrite:
    def test_overwrite_preserves_path(self, store):
        node = _make_node(name="overwrite-test", content="v1")
        path1 = store.write(node)
        node.content = "v2"
        path2 = store.write(node)
        assert path1 == path2
        loaded = store.read(node.id)
        assert loaded.content == "v2"
