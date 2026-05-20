"""Procedure garbage collection: auto-delete failed procedure memories."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode

FAILURE_THRESHOLD = 3
PROCEDURE_TAGS = frozenset({"procedure", "tool-strategy"})


def is_procedure(node: MemoryNode) -> bool:
    """Check if a node is a procedure or tool-strategy memory."""
    return bool(set(t.lower() for t in node.tags) & PROCEDURE_TAGS)


def should_auto_delete(node: MemoryNode) -> bool:
    """Returns True if a procedure memory should be deleted (3+ failures, 0 successes)."""
    if not is_procedure(node):
        return False

    successes = sum(1 for o in node.recent_outcomes if o.get("success"))
    failures = sum(1 for o in node.recent_outcomes if not o.get("success"))

    return failures >= FAILURE_THRESHOLD and successes == 0
