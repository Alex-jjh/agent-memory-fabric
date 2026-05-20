"""MCP Server implementation for Agent Memory Fabric."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_memory_fabric.orchestrator import AMFOrchestrator


class AMFMCPServer:
    """MCP server exposing AMF tools to AI agents.

    Tools:
    - amf_recall: Agent-initiated memory search (reactive path)
    - amf_write: Persist a memory with tags
    - amf_status: Memory corpus statistics
    - amf_transition: Manual state transition
    """

    def __init__(self, orchestrator: "AMFOrchestrator"):
        self.orchestrator = orchestrator

    def amf_recall(self, query: str, top_k: int = 5, scope: str | None = None) -> list[dict]:
        """Agent-initiated memory search. Returns formatted memory dicts."""
        return self.orchestrator.recall(query, top_k=top_k, scope=scope)

    def amf_write(self, content: str, tags: list[str] | None = None, project: str | None = None) -> dict:
        """Write a memory explicitly."""
        node = self.orchestrator.write_explicit(content, tags=tags, project=project)
        if node is None:
            return {"status": "rejected", "reason": "duplicate or secret detected"}
        return {"status": "created", "id": node.id, "name": node.name}

    def amf_status(self) -> dict:
        """Return memory corpus statistics."""
        engine = self.orchestrator.engine
        active = len(engine.list_nodes(state="active"))
        decided = len(engine.list_nodes(state="decided"))
        archived = len(engine.list_nodes(state="archived"))
        return {
            "active": active,
            "decided": decided,
            "archived": archived,
            "total_searchable": active + decided,
        }

    def amf_transition(self, node_id: str, target_state: str, reason: str | None = None) -> dict:
        """Manually transition a memory's lifecycle state."""
        try:
            node = self.orchestrator.engine.transition(node_id, target_state, reason)
            return {"status": "transitioned", "id": node.id, "new_state": node.state.value}
        except ValueError as e:
            return {"status": "error", "reason": str(e)}
