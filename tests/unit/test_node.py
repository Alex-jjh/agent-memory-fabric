"""Tests for MemoryNode model."""

from datetime import datetime, timezone

from agent_memory_fabric.core.node import LifecycleState, MemoryNode


def test_node_creation():
    node = MemoryNode(name="test-node", content="Hello world")
    assert node.state == LifecycleState.ACTIVE
    assert node.decay_score == 1.0
    assert node.access_count == 0
    assert node.id is not None


def test_node_is_retrievable():
    node = MemoryNode(name="active", content="test", state=LifecycleState.ACTIVE)
    assert node.is_retrievable() is True

    archived = MemoryNode(name="archived", content="test", state=LifecycleState.ARCHIVED)
    assert archived.is_retrievable() is False
    assert archived.is_retrievable(include_archived=True) is True

    expired = MemoryNode(name="expired", content="test", state=LifecycleState.EXPIRED)
    assert expired.is_retrievable() is False
    assert expired.is_retrievable(include_archived=True) is False


def test_node_touch():
    node = MemoryNode(name="test", content="test")
    assert node.access_count == 0
    node.touch()
    assert node.access_count == 1
    assert node.last_accessed <= datetime.now(timezone.utc)
