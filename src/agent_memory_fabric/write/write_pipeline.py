"""Write pipeline: orchestrates the full extraction-to-storage flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_memory_fabric.write.chunking import WindowedChunker
from agent_memory_fabric.write.consolidator import Consolidator, ConsolidationDecision
from agent_memory_fabric.write.extractor import ExtractionResult, LLMExtractor, MemoryExtractor
from agent_memory_fabric.write.trigger import WriteTrigger

if TYPE_CHECKING:
    from agent_memory_fabric.core.engine import MemoryEngine
    from agent_memory_fabric.llm.provider import LLMProvider
    from agent_memory_fabric.read.embeddings import EmbeddingProvider


class WritePipeline:
    """Full write orchestration: trigger → chunk → extract → consolidate → persist.

    Usage:
        pipeline = WritePipeline(engine, llm_provider)
        # Each conversation turn:
        pipeline.on_turn(message, has_tool_calls=True)
        # Pipeline auto-extracts when trigger conditions are met
    """

    def __init__(
        self,
        engine: "MemoryEngine",
        llm_provider: "LLMProvider | None" = None,
        embedding_provider: "EmbeddingProvider | None" = None,
        turn_interval: int = 8,
        idle_timeout: float = 120.0,
        turn_size: int = 12,
        past_turn_size: int = 4,
        use_llm_extraction: bool = True,
        use_consolidation: bool = True,
    ):
        self.engine = engine
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider

        self.trigger = WriteTrigger(
            turn_interval=turn_interval,
            idle_timeout_seconds=idle_timeout,
        )
        self.chunker = WindowedChunker(
            turn_size=turn_size,
            past_turn_size=past_turn_size,
        )

        if llm_provider and use_llm_extraction:
            self.extractor = LLMExtractor(provider=llm_provider)
        else:
            self.extractor = MemoryExtractor()

        self.consolidator: Consolidator | None = None
        if llm_provider and use_consolidation:
            self.consolidator = Consolidator(
                llm_provider=llm_provider,
                embedding_provider=embedding_provider,
                sqlite_store=engine.sqlite_store,
            )

        self._turn_buffer: list[str] = []
        self._extraction_count: int = 0
        self._max_buffer_turns: int = 200

    def on_turn(
        self,
        message: str,
        has_tool_calls: bool = False,
        has_save_hint: bool = False,
    ) -> list[str]:
        """Process a conversation turn. Returns IDs of any memories created.

        Call this for each user or assistant message. The pipeline automatically
        extracts when trigger conditions are met.
        """
        self._turn_buffer.append(message)
        self.trigger.record_turn(has_tool_calls=has_tool_calls, has_save_hint=has_save_hint)

        if len(self._turn_buffer) >= self._max_buffer_turns:
            created_ids = self._run_extraction()
            self.trigger.mark_extracted()
            return created_ids

        if not self.trigger.should_extract():
            return []

        created_ids = self._run_extraction()
        self.trigger.mark_extracted()
        return created_ids

    def force_extract(self) -> list[str]:
        """Force extraction regardless of trigger state (e.g., session end)."""
        if not self._turn_buffer:
            return []
        created_ids = self._run_extraction()
        self.trigger.mark_extracted()
        return created_ids

    def _run_extraction(self) -> list[str]:
        """Execute the full extraction pipeline on buffered turns."""
        chunks = self.chunker.chunk_conversation(self._turn_buffer)
        created_ids: list[str] = []

        existing_manifest = self._generate_manifest()

        for chunk in chunks:
            text = "\n".join(chunk.current_turns)
            past_context = "\n".join(chunk.past_turns) if chunk.past_turns else ""
            context = past_context
            if existing_manifest:
                context = f"{past_context}\n\n<existing_memories>\n{existing_manifest}\nOnly extract NEW facts not already listed above.\n</existing_memories>" if past_context else f"<existing_memories>\n{existing_manifest}\nOnly extract NEW facts not already listed above.\n</existing_memories>"

            results = self.extractor.extract(text, context=context or None)

            grounded = self._filter_grounded(results, chunk.current_turns)

            for result in grounded:
                node_id = self._persist(result)
                if node_id:
                    created_ids.append(node_id)

        self._turn_buffer.clear()
        self._extraction_count += 1
        return created_ids

    def _filter_grounded(
        self, results: list[ExtractionResult], current_turns: list[str]
    ) -> list[ExtractionResult]:
        """Citation filtering: only keep results grounded in current chunk."""
        grounded_contents = self.chunker.filter_citations(
            [r.content for r in results],
            current_turns,
        )
        grounded_set = set(grounded_contents)
        return [r for r in results if r.content in grounded_set]

    def _persist(self, result: ExtractionResult) -> str | None:
        """Consolidate and persist a single extraction result."""
        if self.consolidator:
            decision = self.consolidator.consolidate_one(result.content)

            if decision.decision == ConsolidationDecision.SKIP:
                return None

            if decision.decision == ConsolidationDecision.UPDATE and decision.target_node_id and decision.content:
                target = self.engine.read(decision.target_node_id)
                if target:
                    from agent_memory_fabric.write.router import compute_hash
                    old_hash = compute_hash(target.content)
                    target.content = decision.content
                    self.engine.markdown_store.write(target)
                    self.engine.sqlite_store.upsert_node(target, content=target.content)
                    self.engine._content_hashes.discard(old_hash)
                    self.engine._content_hashes.add(compute_hash(target.content))
                    return target.id

        from agent_memory_fabric.write.router import WriteRouter
        ttl = None
        if WriteRouter().has_ttl_pattern(result.content):
            from datetime import datetime, timedelta, timezone
            ttl = datetime.now(timezone.utc) + timedelta(days=7)

        node = self.engine.write(
            content=result.content,
            tags=result.suggested_tags,
            name=result.suggested_name,
            ttl=ttl,
            strength=min(1.0, result.confidence + 0.5),
        )
        return node.id if node else None

    def _generate_manifest(self) -> str:
        """Generate manifest of existing memories for extraction context."""
        from agent_memory_fabric.read.manifest import MemoryManifest
        nodes = [n for n in self.engine.markdown_store.list_all() if n.is_retrievable()]
        if not nodes:
            return ""
        manifest = MemoryManifest(max_lines=50)
        return manifest.generate(nodes)

    @property
    def pending_turns(self) -> int:
        return len(self._turn_buffer)

    @property
    def total_extractions(self) -> int:
        return self._extraction_count
