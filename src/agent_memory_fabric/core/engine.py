"""MemoryEngine — main entry point for AMF operations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.config import AMFConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType, WriteOperation
from agent_memory_fabric.lifecycle.state_machine import StateMachine
from agent_memory_fabric.lifecycle.transitions import (
    InactivityArchivePredicate,
    TemporalDecayPredicate,
    TTLExpirationPredicate,
)
from agent_memory_fabric.storage.graph import build_edges_from_wikilinks, extract_wikilinks
from agent_memory_fabric.storage.markdown import MarkdownStore
from agent_memory_fabric.storage.sqlite_store import SQLiteStore


class MemoryEngine:
    """Central coordinator for all AMF operations."""

    def __init__(self, vault_path: str | Path | None = None, config: AMFConfig | None = None):
        self.config = config or AMFConfig()
        if vault_path:
            self.config.vault_path = Path(vault_path)

        self.markdown_store = MarkdownStore(self.config.vault_path)
        self.sqlite_store = SQLiteStore(self.config.get_db_path())
        self.state_machine = StateMachine(self.config.decay)
        self._predicates = [
            TTLExpirationPredicate(),
            TemporalDecayPredicate(
                decay_threshold=self.config.decay.forget_threshold,
                min_inactive_days=14,
            ),
            InactivityArchivePredicate(inactive_days=30),
        ]

        self._initialize()

    def _initialize(self) -> None:
        self.markdown_store._ensure_dirs()
        self.sqlite_store.initialize()
        self._reconcile()

    def _reconcile(self) -> None:
        fs_nodes = self.markdown_store.list_all()
        self.sqlite_store.reconcile(fs_nodes)
        self._rebuild_edges(fs_nodes)

    def _rebuild_edges(self, nodes: list[MemoryNode]) -> None:
        name_to_id = {n.name: n.id for n in nodes}
        for node in nodes:
            edges = build_edges_from_wikilinks(node.id, node.content, name_to_id)
            for source, target, edge_type, weight in edges:
                self.sqlite_store.add_edge(source, target, edge_type, weight)

    def write(
        self,
        content: str,
        operation: WriteOperation | str | None = None,
        project: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        node_type: MemoryType | str = MemoryType.PROJECT,
        state: LifecycleState = LifecycleState.ACTIVE,
        ttl: datetime | None = None,
        strength: float = 1.0,
    ) -> MemoryNode:
        """Create and persist a new memory node."""
        if name is None:
            words = content.split()[:5]
            name = "-".join(w.lower().strip(".,!?;:") for w in words if w)[:50] or "unnamed"

        if isinstance(node_type, str):
            node_type = MemoryType(node_type)

        now = datetime.now(timezone.utc)
        node = MemoryNode(
            name=name,
            content=content,
            state=state,
            type=node_type,
            project=project,
            created=now,
            modified=now,
            last_accessed=now,
            tags=tags or [],
            ttl=ttl,
            strength=strength,
        )

        file_path = self.markdown_store.write(node)
        self.sqlite_store.upsert_node(node, content=content)

        all_nodes = self.sqlite_store.get_all_nodes()
        name_to_id = {r["name"]: r["id"] for r in all_nodes}
        edges = build_edges_from_wikilinks(node.id, content, name_to_id)
        for source, target, edge_type, weight in edges:
            self.sqlite_store.add_edge(source, target, edge_type, weight)

        return node

    def read(self, node_id: str) -> Optional[MemoryNode]:
        """Read a memory node by ID."""
        return self.markdown_store.read(node_id)

    def list_nodes(
        self,
        scope: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        """List node metadata from the index, optionally filtered."""
        return self.sqlite_store.get_all_nodes(state=state, project=scope)

    def transition(
        self,
        node_id: str,
        target_state: LifecycleState | str,
        reason: str | None = None,
    ) -> MemoryNode:
        """Manually trigger a state transition."""
        node = self.markdown_store.read(node_id)
        if node is None:
            raise ValueError(f"Node not found: {node_id}")

        if isinstance(target_state, str):
            target_state = LifecycleState(target_state)

        self.state_machine.transition(node, target_state)
        node.modified = datetime.now(timezone.utc)
        self.markdown_store.write(node)
        self.sqlite_store.upsert_node(node, content=node.content)
        return node

    def run_transitions(self) -> list[tuple[str, LifecycleState, LifecycleState]]:
        """Evaluate all transition predicates on active nodes. Returns transitions fired."""
        transitions_fired: list[tuple[str, LifecycleState, LifecycleState]] = []
        active_nodes = self.sqlite_store.get_all_nodes(state="active")
        decided_nodes = self.sqlite_store.get_all_nodes(state="decided")

        for row in active_nodes + decided_nodes:
            node = self.markdown_store.read(row["id"])
            if node is None:
                continue

            for predicate in self._predicates:
                target = predicate.evaluate(node)
                if target is not None and self.state_machine.can_transition(node, target):
                    old_state = node.state
                    self.state_machine.transition(node, target)
                    node.modified = datetime.now(timezone.utc)
                    self.markdown_store.write(node)
                    self.sqlite_store.upsert_node(node, content=node.content)
                    transitions_fired.append((node.id, old_state, target))
                    break

        return transitions_fired

    def search(
        self,
        query: str,
        top_k: int = 5,
        scope: str | None = None,
        include_archived: bool = False,
    ) -> list[MemoryNode]:
        """Search memories by keyword (FTS5). Returns nodes ranked by BM25."""
        results = self.sqlite_store.search_fts(query, limit=top_k * 3)

        nodes: list[MemoryNode] = []
        for node_id, score in results:
            node = self.markdown_store.read(node_id)
            if node is None:
                continue
            if not node.is_retrievable(include_archived=include_archived):
                continue
            if scope and node.project != scope:
                continue
            node.touch()
            nodes.append(node)
            if len(nodes) >= top_k:
                break

        return nodes
