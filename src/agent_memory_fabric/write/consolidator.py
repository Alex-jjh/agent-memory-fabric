"""Retrieve-then-consolidate: deduplicate and merge memories via LLM arbitration."""

from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from agent_memory_fabric.llm.provider import LLMProvider
    from agent_memory_fabric.read.embeddings import EmbeddingProvider
    from agent_memory_fabric.storage.sqlite_store import SQLiteStore


class ConsolidationDecision(str, Enum):
    ADD = "add"
    UPDATE = "update"
    SKIP = "skip"


class ConsolidationResult(BaseModel):
    decision: ConsolidationDecision
    content: str | None = None
    target_node_id: str | None = None
    reason: str = ""


_CONSOLIDATION_SYSTEM = """You are a memory consolidation agent. Given a NEW memory and EXISTING similar memories, decide:

1. ADD: The new memory contains genuinely new information not covered by existing ones.
2. UPDATE: The new memory updates/refines an existing memory. Provide the merged content.
3. SKIP: The new memory is a duplicate or subset of existing memories.

Output exactly one JSON object:
{"decision": "add|update|skip", "target_id": null or "id_to_update", "merged_content": null or "merged text", "reason": "brief explanation"}

Rules:
- Preserve timestamps, specific numbers, and proper nouns from both sources
- When updating, merge information (don't discard old details unless contradicted)
- SKIP only if the new memory adds zero new information
- Prefer ADD over SKIP when uncertain"""

_CONSOLIDATION_USER = """NEW MEMORY:
{new_content}

EXISTING SIMILAR MEMORIES:
{existing_memories}

Decide: ADD, UPDATE, or SKIP?"""


class Consolidator:
    """Retrieve-then-consolidate pipeline for memory deduplication.

    For each new memory:
    1. Vector search top-K most similar existing memories
    2. LLM decides: Add (new info) / Update (merge) / Skip (duplicate)
    3. Fallback to Add on any failure (never lose data)
    """

    def __init__(
        self,
        llm_provider: "LLMProvider",
        embedding_provider: "EmbeddingProvider | None" = None,
        sqlite_store: "SQLiteStore | None" = None,
        similar_k: int = 2,
        batch_size: int = 4,
        similarity_threshold: float = 0.3,
    ):
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.sqlite_store = sqlite_store
        self.similar_k = similar_k
        self.batch_size = batch_size
        self.similarity_threshold = similarity_threshold

    def consolidate_one(self, new_content: str) -> ConsolidationResult:
        """Decide how to handle a single new memory against existing corpus."""
        similar = self._retrieve_similar(new_content)

        if not similar:
            return ConsolidationResult(decision=ConsolidationDecision.ADD, reason="no similar memories found")

        try:
            return self._llm_decide(new_content, similar)
        except Exception:
            return ConsolidationResult(decision=ConsolidationDecision.ADD, reason="fallback: LLM error")

    def consolidate_batch(self, contents: list[str]) -> list[ConsolidationResult]:
        """Process multiple new memories. Each is consolidated independently."""
        results: list[ConsolidationResult] = []
        for i in range(0, len(contents), self.batch_size):
            batch = contents[i:i + self.batch_size]
            for content in batch:
                results.append(self.consolidate_one(content))
        return results

    def _retrieve_similar(self, content: str) -> list[tuple[str, str]]:
        """Retrieve top-K similar existing memories as (id, content) pairs."""
        if not self.sqlite_store:
            return []

        if self.embedding_provider:
            try:
                embedding = self.embedding_provider.embed(content)
                results = self.sqlite_store.search_vector(embedding, limit=self.similar_k)
                if results:
                    return self._load_contents(results)
            except Exception:
                pass

        try:
            fts_results = self.sqlite_store.search_fts(content, limit=self.similar_k)
            if fts_results:
                return self._load_contents(fts_results)
        except Exception:
            pass

        return []

    def _load_contents(self, search_results: list[tuple[str, float]]) -> list[tuple[str, str]]:
        """Load node content for search results."""
        contents: list[tuple[str, str]] = []
        for node_id, _score in search_results:
            node_data = self.sqlite_store.get_node(node_id)
            if not node_data:
                continue
            content = self._get_content_for_node(node_id, node_data)
            if content:
                contents.append((node_id, content))
        return contents

    def _get_content_for_node(self, node_id: str, node_data: dict) -> str:
        """Retrieve full content for a node. Tries FTS, falls back to name."""
        if hasattr(self.sqlite_store, '_get_conn'):
            try:
                conn = self.sqlite_store._get_conn()
                row = conn.execute(
                    "SELECT content FROM fts_index WHERE node_id = ?", (node_id,)
                ).fetchone()
                if row and row[0]:
                    return row[0]
            except Exception:
                pass
        return node_data.get("content", "") or node_data.get("name", "")

    def _llm_decide(self, new_content: str, similar: list[tuple[str, str]]) -> ConsolidationResult:
        """Ask LLM to decide consolidation action."""
        existing_formatted = "\n".join(
            f"[ID: {nid}] {content}" for nid, content in similar
        )

        user_prompt = _CONSOLIDATION_USER.format(
            new_content=new_content,
            existing_memories=existing_formatted,
        )

        response = self.llm_provider.complete(_CONSOLIDATION_SYSTEM, user_prompt)
        return self._parse_response(response)

    def _parse_response(self, response: str) -> ConsolidationResult:
        """Parse LLM JSON response into ConsolidationResult."""
        response = response.strip()
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1:
            return ConsolidationResult(decision=ConsolidationDecision.ADD, reason="fallback: no JSON in response")

        try:
            data = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return ConsolidationResult(decision=ConsolidationDecision.ADD, reason="fallback: invalid JSON")

        decision_str = data.get("decision", "add").lower()
        try:
            decision = ConsolidationDecision(decision_str)
        except ValueError:
            decision = ConsolidationDecision.ADD

        return ConsolidationResult(
            decision=decision,
            content=data.get("merged_content"),
            target_node_id=data.get("target_id"),
            reason=data.get("reason", ""),
        )
