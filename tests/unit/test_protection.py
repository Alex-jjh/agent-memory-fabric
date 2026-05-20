"""Tests for lifecycle protection rules."""

import pytest

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType
from agent_memory_fabric.lifecycle.protection import is_protected


def _make_node(**kwargs) -> MemoryNode:
    defaults = {"id": "test-1", "name": "test", "content": "test content"}
    defaults.update(kwargs)
    return MemoryNode(**defaults)


class TestIsProtected:
    def test_user_type_always_protected(self):
        node = _make_node(type=MemoryType.USER)
        assert is_protected(node) is True

    def test_project_type_not_protected_by_default(self):
        node = _make_node(type=MemoryType.PROJECT)
        assert is_protected(node) is False

    def test_profile_tag_protects(self):
        node = _make_node(tags=["profile", "session:s1"])
        assert is_protected(node) is True

    def test_preference_tag_protects(self):
        node = _make_node(tags=["preference"])
        assert is_protected(node) is True

    def test_pinned_tag_protects(self):
        node = _make_node(tags=["pinned"])
        assert is_protected(node) is True

    def test_user_stated_tag_protects(self):
        node = _make_node(tags=["user-stated"])
        assert is_protected(node) is True

    def test_provenance_explicit_tag_protects(self):
        node = _make_node(tags=["provenance:user_explicit"])
        assert is_protected(node) is True

    def test_provenance_inferred_not_protected(self):
        node = _make_node(tags=["provenance:inferred"])
        assert is_protected(node) is False

    def test_random_tags_not_protected(self):
        node = _make_node(tags=["session:s1", "speaker:User", "topic:work"])
        assert is_protected(node) is False

    def test_case_insensitive_tags(self):
        node = _make_node(tags=["Profile"])
        assert is_protected(node) is True
