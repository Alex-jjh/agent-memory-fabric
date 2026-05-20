"""SQLite sidecar — derived index for metadata, vectors, graph edges, and FTS."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.node import MemoryNode


class SQLiteStore:
    """SQLite sidecar database (.amf/index.db).

    Tables:
    - nodes: id, name, state, type, project, created, modified, last_accessed,
             access_count, decay_score, strength, ttl, tags (JSON)
    - embeddings: node_id, vector (blob, via sqlite-vec)
    - edges: source_id, target_id, edge_type, weight
    - fts_content: FTS5 virtual table for full-text search on node content

    This is a DERIVED index — Markdown files are source of truth.
    On startup, reconcile DB state with filesystem.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        raise NotImplementedError("Phase 1")

    def upsert_node(self, node: MemoryNode) -> None:
        """Insert or update a node's metadata in the index."""
        raise NotImplementedError("Phase 1")

    def delete_node(self, node_id: str) -> None:
        """Remove a node from the index."""
        raise NotImplementedError("Phase 1")

    def search_fts(self, query: str, limit: int = 10) -> list[str]:
        """Full-text search. Returns matching node IDs."""
        raise NotImplementedError("Phase 1")

    def search_vector(self, embedding: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Vector similarity search. Returns (node_id, distance) pairs."""
        raise NotImplementedError("Phase 3")

    def get_neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]:
        """Get graph neighbors for a node."""
        raise NotImplementedError("Phase 3")

    def upsert_embedding(self, node_id: str, embedding: list[float]) -> None:
        """Store or update embedding for a node."""
        raise NotImplementedError("Phase 3")

    def add_edge(self, source_id: str, target_id: str, edge_type: str, weight: float = 1.0) -> None:
        """Add a graph edge between two nodes."""
        raise NotImplementedError("Phase 1")

    def reconcile(self, filesystem_nodes: list[MemoryNode]) -> None:
        """Sync DB index with filesystem state (filesystem wins on conflict)."""
        raise NotImplementedError("Phase 1")
