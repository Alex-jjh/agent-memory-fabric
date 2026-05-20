"""AMF Orchestrator — the top-level entry point for using Agent Memory Fabric.

Provides a simple, batteries-included interface that wires together the full
read and write pipelines. This is the class external consumers should use.

Usage:
    from agent_memory_fabric import AMFOrchestrator

    amf = AMFOrchestrator(vault_path="~/my-vault")

    # On each conversation turn:
    context = amf.on_user_message("I prefer dark mode in all editors")
    # context is an XML string to inject into the LLM prompt

    # On tool success (for anti-pattern self-correction):
    amf.on_tool_success("git")

    # Periodic maintenance:
    amf.run_maintenance()
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.config import AMFConfig
from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.lifecycle.anti_pattern import AntiPatternTracker
from agent_memory_fabric.llm.provider import LLMProvider
from agent_memory_fabric.read.embeddings import EmbeddingProvider
from agent_memory_fabric.read.gateway import ProactiveGateway
from agent_memory_fabric.read.injection import format_interpretation_rules, format_memories_xml, inject_into_message
from agent_memory_fabric.read.manifest import MemoryManifest
from agent_memory_fabric.read.query_expansion import QueryExpander
from agent_memory_fabric.write.write_pipeline import WritePipeline


class AMFOrchestrator:
    """Batteries-included orchestrator for Agent Memory Fabric.

    Wires together: engine, write pipeline, read gateway, anti-pattern tracking,
    and lifecycle maintenance into a single coherent interface.
    """

    def __init__(
        self,
        vault_path: str | Path | None = None,
        config: AMFConfig | None = None,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        use_llm_extraction: bool = True,
        use_consolidation: bool = True,
        async_extraction: bool = False,
        total_budget_tokens: int = 4000,
    ):
        self.config = config or AMFConfig()
        if vault_path:
            self.config.vault_path = Path(vault_path)

        self.engine = MemoryEngine(config=self.config)
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider

        self.write_pipeline = WritePipeline(
            engine=self.engine,
            llm_provider=llm_provider,
            embedding_provider=embedding_provider,
            use_llm_extraction=use_llm_extraction,
            use_consolidation=use_consolidation,
        )

        self.async_pipeline = None
        if async_extraction:
            from agent_memory_fabric.write.async_pipeline import AsyncWritePipeline
            self.async_pipeline = AsyncWritePipeline(self.write_pipeline)

        self.gateway = ProactiveGateway(
            sqlite_store=self.engine.sqlite_store,
            scorer=self.engine.scorer,
            config=self.config.retriever,
            embedding_provider=embedding_provider,
            total_budget_tokens=total_budget_tokens,
        )

        if llm_provider:
            from agent_memory_fabric.read.reranker import LLMReranker
            self.gateway.reranker = LLMReranker(provider=llm_provider)

        self.anti_pattern_tracker = AntiPatternTracker()
        self.query_expander = QueryExpander()
        self._interpretation_rules: str = format_interpretation_rules()
        self._manifest = MemoryManifest()

    def on_user_message(
        self,
        message: str,
        has_tool_calls: bool = False,
        has_save_hint: bool = False,
        scope: str | None = None,
        active_domain: str | None = None,
    ) -> str:
        """Process a user message: retrieve context first, then extract for future turns.

        Returns XML string to inject into the LLM prompt (empty if abstaining).
        """
        self.anti_pattern_tracker.clear_turn()

        # Expand short queries with prior turn context
        retrieval_query = self.query_expander.expand(message)
        self.query_expander.record_turn("user", message)

        # Retrieve BEFORE write to avoid same-turn echo
        candidates = self._get_candidates(scope)
        scored = self.gateway.retrieve(
            retrieval_query, candidates, scope=scope, active_domain=active_domain,
        )

        # Write pipeline runs after retrieval (extractions available for future turns)
        if self.async_pipeline:
            self.async_pipeline.schedule_turn(message, has_tool_calls=has_tool_calls, has_save_hint=has_save_hint)
        else:
            self.write_pipeline.on_turn(message, has_tool_calls=has_tool_calls, has_save_hint=has_save_hint)

        if not scored:
            return ""

        for sm in scored:
            self.anti_pattern_tracker.record_injection(sm.node)

        return format_memories_xml(scored)

    def on_assistant_message(
        self,
        message: str,
        has_tool_calls: bool = False,
    ) -> list[str]:
        """Process an assistant message for extraction only. Returns created memory IDs."""
        self.query_expander.record_turn("assistant", message)
        return self.write_pipeline.on_turn(message, has_tool_calls=has_tool_calls)

    def on_tool_success(self, tool_name: str) -> list[str]:
        """Record a tool success, degrading contradicted anti-patterns.

        Returns IDs of degraded anti-pattern memories.
        """
        contradicted = self.anti_pattern_tracker.get_contradicted(tool_name)
        for node_id in contradicted:
            self.engine.update_confidence(node_id, success=False)
        return contradicted

    def on_session_end(self) -> list[str]:
        """Force extraction of any remaining buffered turns and reset session state."""
        self.query_expander.reset()
        if self.async_pipeline:
            return self.async_pipeline.flush()
        return self.write_pipeline.force_extract()

    def run_maintenance(self) -> dict[str, int]:
        """Run periodic maintenance: transitions + trim."""
        transitions = self.engine.run_transitions()
        trimmed = self.engine.run_trim()
        return {
            "transitions": len(transitions),
            "trimmed": trimmed,
        }

    def get_manifest(self, scope: str | None = None) -> str:
        """Get the memory manifest for system prompt injection.

        Returns a scannable index of all memories (sorted newest-first, truncated).
        The LLM uses this to know what memories exist without reading full content.
        """
        candidates = self._get_candidates(scope)
        return self._manifest.generate_cached(candidates, cache_key=scope or "_global")

    def get_interpretation_rules(self) -> str:
        """Get the interpretation rules section for system prompt."""
        return self._interpretation_rules

    def recall(self, query: str, top_k: int = 5, scope: str | None = None) -> list[dict]:
        """Agent-initiated reactive memory search. Returns formatted dicts."""
        results = self.engine.search(query, top_k=top_k, scope=scope)
        return [
            {
                "id": n.id,
                "content": n.content,
                "type": n.type.value,
                "confidence": round(n.confidence_alpha / (n.confidence_alpha + n.confidence_beta), 2),
                "tags": n.tags,
                "last_accessed": n.last_accessed.isoformat(),
            }
            for n in results
        ]

    def search(self, query: str, top_k: int = 5, scope: str | None = None) -> list[MemoryNode]:
        """Direct search (bypasses full pipeline). Useful for tools/debugging."""
        return self.engine.search(query, top_k=top_k, scope=scope)

    def write_explicit(
        self,
        content: str,
        tags: list[str] | None = None,
        project: str | None = None,
    ) -> Optional[MemoryNode]:
        """Directly write a memory (bypasses extraction pipeline). For user-explicit saves."""
        final_tags = list(tags or [])
        if "provenance:user_explicit" not in final_tags:
            final_tags.append("provenance:user_explicit")
        return self.engine.write(content=content, tags=final_tags, project=project)

    def _get_candidates(self, scope: str | None = None) -> list[MemoryNode]:
        """Load retrievable candidates: always includes global, plus scoped if specified."""
        global_nodes = self.engine.markdown_store.list_all(scope=None)
        if scope:
            scoped_nodes = self.engine.markdown_store.list_all(scope=scope)
            seen_ids = {n.id for n in global_nodes}
            all_nodes = global_nodes + [n for n in scoped_nodes if n.id not in seen_ids]
        else:
            all_nodes = global_nodes
        return [n for n in all_nodes if n.is_retrievable()]
