"""Lifecycle state machine — manages valid transitions and enforces invariants."""

from __future__ import annotations

from agent_memory_fabric.core.config import DecayConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode

VALID_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.ACTIVE: {LifecycleState.DECIDED, LifecycleState.ARCHIVED, LifecycleState.EXPIRED},
    LifecycleState.DECIDED: {LifecycleState.ACTIVE, LifecycleState.ARCHIVED, LifecycleState.EXPIRED},
    LifecycleState.ARCHIVED: {LifecycleState.ACTIVE, LifecycleState.EXPIRED},
    LifecycleState.EXPIRED: set(),  # terminal state
}


class StateMachine:
    """Evaluates and executes lifecycle state transitions."""

    def __init__(self, decay_config: DecayConfig):
        self.decay_config = decay_config

    def can_transition(self, node: MemoryNode, target: LifecycleState) -> bool:
        return target in VALID_TRANSITIONS.get(node.state, set())

    def transition(self, node: MemoryNode, target: LifecycleState) -> MemoryNode:
        if not self.can_transition(node, target):
            raise ValueError(
                f"Invalid transition: {node.state.value} -> {target.value} "
                f"for node {node.id}"
            )
        node.state = target
        return node

    def evaluate_predicates(self, node: MemoryNode) -> LifecycleState | None:
        """Evaluate all transition predicates for a node. Returns target state or None."""
        raise NotImplementedError("Phase 2: predicate evaluation")
