"""Tests for lifecycle state machine."""

import pytest

from agent_memory_fabric.core.config import DecayConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.lifecycle.state_machine import StateMachine


@pytest.fixture
def sm():
    return StateMachine(DecayConfig())


def test_valid_transitions(sm: StateMachine):
    node = MemoryNode(name="test", content="test", state=LifecycleState.ACTIVE)
    assert sm.can_transition(node, LifecycleState.DECIDED) is True
    assert sm.can_transition(node, LifecycleState.ARCHIVED) is True
    assert sm.can_transition(node, LifecycleState.EXPIRED) is True


def test_expired_is_terminal(sm: StateMachine):
    node = MemoryNode(name="test", content="test", state=LifecycleState.EXPIRED)
    assert sm.can_transition(node, LifecycleState.ACTIVE) is False
    assert sm.can_transition(node, LifecycleState.DECIDED) is False
    assert sm.can_transition(node, LifecycleState.ARCHIVED) is False


def test_transition_executes(sm: StateMachine):
    node = MemoryNode(name="test", content="test", state=LifecycleState.ACTIVE)
    result = sm.transition(node, LifecycleState.DECIDED)
    assert result.state == LifecycleState.DECIDED


def test_invalid_transition_raises(sm: StateMachine):
    node = MemoryNode(name="test", content="test", state=LifecycleState.EXPIRED)
    with pytest.raises(ValueError, match="Invalid transition"):
        sm.transition(node, LifecycleState.ACTIVE)
