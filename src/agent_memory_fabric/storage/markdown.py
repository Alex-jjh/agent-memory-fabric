"""Markdown file storage — source of truth for memory nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.node import MemoryNode


class MarkdownStore:
    """Reads/writes MemoryNodes as Markdown files with YAML frontmatter.

    File layout:
        vault_path/
        ├── _global/          (Global scope memories)
        ├── projects/
        │   └── {project}/    (Project scope memories)
        └── _sessions/        (Session scratch, auto-cleanup)

    Each memory is one .md file:
        ---
        id: ...
        name: ...
        state: active
        ...
        ---
        Content body here.
    """

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path

    def read(self, node_id: str) -> Optional[MemoryNode]:
        """Read a memory node from its Markdown file."""
        raise NotImplementedError("Phase 1")

    def write(self, node: MemoryNode) -> Path:
        """Write a memory node to a Markdown file. Returns the file path."""
        raise NotImplementedError("Phase 1")

    def delete(self, node_id: str) -> bool:
        """Delete a memory file. Returns True if file existed."""
        raise NotImplementedError("Phase 1")

    def list_all(self, scope: str | None = None) -> list[MemoryNode]:
        """List all memory nodes, optionally filtered by scope/project."""
        raise NotImplementedError("Phase 1")

    def resolve_path(self, node: MemoryNode) -> Path:
        """Determine file path for a node based on its scope."""
        if node.project:
            return self.vault_path / "projects" / node.project / f"{node.name}.md"
        return self.vault_path / "_global" / f"{node.name}.md"
