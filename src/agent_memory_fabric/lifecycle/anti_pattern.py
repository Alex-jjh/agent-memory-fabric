"""Anti-pattern self-correction: degrade anti-patterns when warned-against tools succeed."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode


class AntiPatternTracker:
    """Tracks injected anti-pattern memories and auto-degrades on contradiction.

    When a tool succeeds but an injected anti-pattern warned against it
    (matched via tags), the anti-pattern's confidence is reduced.
    """

    def __init__(self):
        self._injected: dict[str, set[str]] = {}  # node_id -> lowercase_tags

    def record_injection(self, node: MemoryNode) -> None:
        """Record that an anti-pattern memory was injected this turn."""
        if "anti-pattern" in {t.lower() for t in node.tags}:
            tags = {t.lower() for t in node.tags} - {"anti-pattern"}
            self._injected[node.id] = tags

    def record_injections(self, nodes: list[MemoryNode]) -> None:
        for node in nodes:
            self.record_injection(node)

    def get_contradicted(self, tool_name: str) -> list[str]:
        """Return node IDs of anti-patterns that warned against a tool that just succeeded."""
        tool_lower = tool_name.lower()
        contradicted = []
        for node_id, tags in self._injected.items():
            if tool_lower in tags:
                contradicted.append(node_id)
        return contradicted

    def clear_turn(self) -> None:
        """Reset for next turn."""
        self._injected.clear()

    @property
    def active_count(self) -> int:
        return len(self._injected)
