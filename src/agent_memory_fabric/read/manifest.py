"""Memory manifest: one-line index of all memories for LLM visibility."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from agent_memory_fabric.core.node import MemoryNode

MAX_LINES = 200
MAX_BYTES = 25_000


class MemoryManifest:
    """Generates a scannable index of all memories.

    The manifest lets the LLM know what memories exist without loading full content.
    Format: `- [type] name (timestamp): first_sentence`
    Sorted newest-first by modified timestamp, truncated to limits.
    """

    def __init__(self, max_lines: int = MAX_LINES, max_bytes: int = MAX_BYTES):
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self._cache: str | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 60.0

    def generate(self, nodes: list[MemoryNode]) -> str:
        """Generate manifest from memory nodes, sorted newest-first."""
        if not nodes:
            return ""

        sorted_nodes = sorted(nodes, key=lambda n: n.modified, reverse=True)
        lines: list[str] = []
        for node in sorted_nodes:
            line = self._format_entry(node)
            lines.append(line)
            if len(lines) >= self.max_lines:
                break

        manifest = "\n".join(lines)
        return self._truncate_bytes(manifest)

    def generate_cached(self, nodes: list[MemoryNode]) -> str:
        """Generate with TTL-based caching."""
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache
        self._cache = self.generate(nodes)
        self._cache_time = now
        return self._cache

    def invalidate_cache(self) -> None:
        self._cache = None

    def _format_entry(self, node: MemoryNode) -> str:
        """Format: '- [type] name (ISO date): first_sentence'"""
        timestamp = node.modified.strftime("%Y-%m-%d %H:%M")
        description = self._first_sentence(node.content)
        return f"- [{node.type.value}] {node.name} ({timestamp}): {description}"

    def _first_sentence(self, content: str) -> str:
        """Extract first sentence or first 80 chars, whichever is shorter."""
        content = content.strip()
        for sep in (".", "!", "?", "\n"):
            idx = content.find(sep)
            if 0 < idx < 120:
                return content[:idx + 1]
        return content[:80] + ("..." if len(content) > 80 else "")

    def _truncate_bytes(self, manifest: str) -> str:
        """Enforce byte limit by removing trailing lines."""
        encoded = manifest.encode("utf-8")
        if len(encoded) <= self.max_bytes:
            return manifest
        truncated = encoded[:self.max_bytes].decode("utf-8", errors="ignore")
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        return truncated
