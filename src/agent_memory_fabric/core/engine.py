"""MemoryEngine — main entry point for AMF operations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.config import AMFConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode, WriteOperation
from agent_memory_fabric.lifecycle.state_machine import StateMachine
from agent_memory_fabric.read.scorer import MultiSignalScorer
from agent_memory_fabric.storage.markdown import MarkdownStore
from agent_memory_fabric.storage.sqlite_store import SQLiteStore
from agent_memory_fabric.write.router import WriteRouter


class MemoryEngine:
    """Central coordinator for all AMF operations."""

    def __init__(self, vault_path: str | Path | None = None, config: AMFConfig | None = None):
        self.config = config or AMFConfig()
        if vault_path:
            self.config.vault_path = Path(vault_path)

        self.markdown_store = MarkdownStore(self.config.vault_path)
        self.sqlite_store = SQLiteStore(self.config.get_db_path())
        self.state_machine = StateMachine(self.config.decay)
        self.write_router = WriteRouter()
        self.scorer = MultiSignalScorer(self.config.scorer_weights)

    def write(
        self,
        content: str,
        operation: WriteOperation | str | None = None,
        project: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> MemoryNode:
        """Classify and persist a memory. Returns the created/updated node."""
        raise NotImplementedError("Phase 1")

    def retrieve_proactive(
        self,
        message: str,
        scope: str | None = None,
        top_k: int | None = None,
    ) -> list[MemoryNode]:
        """Proactive retrieval: select relevant memories for an incoming message."""
        raise NotImplementedError("Phase 3")

    def search(
        self,
        query: str,
        top_k: int = 5,
        scope: str | None = None,
        include_archived: bool = False,
    ) -> list[MemoryNode]:
        """Explicit search across the memory corpus."""
        raise NotImplementedError("Phase 3")

    def run_transitions(self) -> list[tuple[str, LifecycleState, LifecycleState]]:
        """Evaluate all transition predicates. Returns list of (node_id, old_state, new_state)."""
        raise NotImplementedError("Phase 2")

    def run_consolidation(self) -> int:
        """Merge duplicates and synthesize insights. Returns count of nodes affected."""
        raise NotImplementedError("Phase 2")

    def transition(
        self,
        node_id: str,
        target_state: LifecycleState | str,
        reason: str | None = None,
    ) -> MemoryNode:
        """Manually trigger a state transition."""
        raise NotImplementedError("Phase 2")
