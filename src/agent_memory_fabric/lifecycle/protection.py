"""Protected memory categories — memories that should never be auto-expired or trimmed."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode, MemoryType

PROTECTED_TAGS = frozenset({"profile", "preference", "user-stated", "pinned"})
PROTECTED_PROVENANCES = frozenset({"user_explicit", "pinned"})


def is_protected(node: MemoryNode) -> bool:
    """Check if a memory node is protected from automatic lifecycle transitions.

    Protected memories are never auto-archived, auto-expired, or trimmed.
    They can still be manually transitioned by the user.
    """
    if node.type == MemoryType.USER:
        return True
    node_tags = set(t.lower() for t in node.tags)
    if node_tags & PROTECTED_TAGS:
        return True
    if any(t.startswith("provenance:") and t.split(":", 1)[1] in PROTECTED_PROVENANCES for t in node_tags):
        return True
    return False
