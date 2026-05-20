"""LLM-as-reranker: use a fast model to select the most relevant memories from candidates."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agent_memory_fabric.read.scorer import ScoredMemory

if TYPE_CHECKING:
    from agent_memory_fabric.llm.provider import LLMProvider

_RERANKER_SYSTEM = """You are a memory relevance ranker. Given a user query and a list of memory candidates, select the most relevant memories by ID.

Rules:
- Select up to {top_k} memories that would be most useful for answering the query
- Prefer memories that directly answer the question over tangentially related ones
- Prefer recent memories over old ones when relevance is similar
- Return ONLY valid JSON: {{"selected_memories": ["id1", "id2", ...]}}
- If no memories are relevant, return: {{"selected_memories": []}}"""

_RERANKER_USER = """User query: {query}

Memory candidates:
{candidates}

Select the most relevant memories (up to {top_k}). Return JSON only:"""


class LLMReranker:
    """Reranks retrieval candidates using an LLM for semantic understanding.

    After algorithmic scoring returns ~20 candidates, the reranker sends
    their summaries to a fast model (e.g., Haiku) which selects the top-K
    most relevant. Falls back to algorithmic top-K on any failure.
    """

    def __init__(
        self,
        provider: "LLMProvider",
        max_candidates: int = 20,
        top_k: int = 5,
    ):
        self.provider = provider
        self.max_candidates = max_candidates
        self.top_k = top_k

    def rerank(self, query: str, candidates: list[ScoredMemory]) -> list[ScoredMemory]:
        """Rerank candidates using LLM. Falls back to score-based top-K on failure."""
        if len(candidates) <= self.top_k:
            return candidates

        candidates = candidates[:self.max_candidates]

        try:
            return self._llm_select(query, candidates)
        except Exception:
            return self._fallback(candidates)

    def _llm_select(self, query: str, candidates: list[ScoredMemory]) -> list[ScoredMemory]:
        """Send candidate manifest to LLM and parse selection."""
        manifest = self._build_manifest(candidates)
        system = _RERANKER_SYSTEM.format(top_k=self.top_k)
        user = _RERANKER_USER.format(query=query, candidates=manifest, top_k=self.top_k)

        response = self.provider.complete(system, user)
        selected_ids = self._parse_response(response)

        if not selected_ids:
            return self._fallback(candidates)

        id_to_sm = {sm.node.id: sm for sm in candidates}
        result = [id_to_sm[sid] for sid in selected_ids if sid in id_to_sm]
        if not result:
            return self._fallback(candidates)
        # Pad with algorithmic top if LLM returned fewer than top_k
        if len(result) < self.top_k:
            selected_set = {sm.node.id for sm in result}
            for sm in candidates:
                if sm.node.id not in selected_set:
                    result.append(sm)
                    if len(result) >= self.top_k:
                        break
        return result

    def _build_manifest(self, candidates: list[ScoredMemory]) -> str:
        """One-line summary per candidate for the LLM."""
        lines: list[str] = []
        for sm in candidates:
            content_preview = sm.node.content[:80].replace("\n", " ")
            lines.append(f"[{sm.node.id}] ({sm.node.type.value}) {content_preview}")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> list[str]:
        """Parse JSON response to extract selected memory IDs."""
        response = response.strip()
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(response[start:end + 1])
            selected = data.get("selected_memories", [])
            if isinstance(selected, list):
                return [s for s in selected if isinstance(s, str)]
        except (json.JSONDecodeError, ValueError):
            pass
        return []

    def _fallback(self, candidates: list[ScoredMemory]) -> list[ScoredMemory]:
        """Algorithmic fallback: return top-K by score."""
        return candidates[:self.top_k]
