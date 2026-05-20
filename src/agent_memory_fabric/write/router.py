"""Write Router — classifies incoming information into write operation types."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode, WriteOperation


class WriteRouter:
    """Classifies incoming content into one of 6 write operations.

    Classification hierarchy:
    1. Explicit operation (user/agent specified)
    2. Conflict detection (contradicts existing → Replace)
    3. Temporal detection (has expiry → Expire)
    4. Convergence detection (multiple related Active → Synthesize)
    5. Default: Append
    """

    def classify(
        self,
        content: str,
        existing_node: MemoryNode | None = None,
        related_nodes: list[MemoryNode] | None = None,
    ) -> WriteOperation:
        """Determine the appropriate write operation for incoming content."""
        raise NotImplementedError("Phase 2: write classification")

    def execute(
        self,
        content: str,
        operation: WriteOperation,
        target_node: MemoryNode | None = None,
    ) -> MemoryNode:
        """Execute the classified write operation."""
        raise NotImplementedError("Phase 2: write execution")
