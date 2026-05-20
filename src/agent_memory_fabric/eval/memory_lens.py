"""MemoryLens: intrinsic quality evaluation of the memory corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent_memory_fabric.core.node import MemoryNode

if TYPE_CHECKING:
    from agent_memory_fabric.llm.provider import LLMProvider
    from agent_memory_fabric.read.embeddings import EmbeddingProvider


@dataclass
class MemoryLensReport:
    faithfulness: float = 0.0
    redundancy_rate: float = 0.0
    conflict_rate: float = 0.0
    compression_rate: float = 0.0
    sample_size: int = 0
    details: dict = field(default_factory=dict)


_FAITHFULNESS_SYSTEM = """You are evaluating whether a memory is grounded in the source conversation.
A memory is faithful if:
1. The information is explicitly stated or directly implied in the source
2. It does not add significant details not present in the source
3. It does not contradict the source

Respond with ONLY: {"faithful": true/false, "reason": "brief explanation"}"""

_FAITHFULNESS_USER = """Source conversation:
{source}

Memory to evaluate:
{memory}

Is this memory faithful to the source?"""

_CONFLICT_SYSTEM = """You are evaluating whether two memories contradict each other.
Two memories conflict if:
1. They make contradictory claims about the same subject
2. They have mutually exclusive properties
3. They have irreconcilable timeline inconsistencies

Respond with ONLY: {"conflict": true/false, "reason": "brief explanation"}"""

_CONFLICT_USER = """Memory A:
{memory_a}

Memory B:
{memory_b}

Do these memories conflict?"""


class MemoryLens:
    """Intrinsic quality evaluation of the memory corpus.

    Metrics:
    - Faithfulness: Are memories grounded in source conversations?
    - Redundancy: Semantic duplication rate
    - ConflictRate: Factual contradiction detection
    - CompressionRate: Memory tokens / raw source tokens
    """

    def __init__(
        self,
        llm_provider: "LLMProvider | None" = None,
        embedding_provider: "EmbeddingProvider | None" = None,
        sample_size: int = 50,
    ):
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.sample_size = sample_size

    def evaluate(
        self,
        nodes: list[MemoryNode],
        source_text: str | None = None,
        source_tokens: int | None = None,
    ) -> MemoryLensReport:
        """Run full evaluation suite on memory corpus."""
        sample = nodes[:self.sample_size]

        report = MemoryLensReport(sample_size=len(sample))
        report.compression_rate = self._compression_rate(nodes, source_tokens)
        report.redundancy_rate = self._redundancy_rate(sample)

        if self.llm_provider:
            if source_text:
                report.faithfulness = self._faithfulness(sample, source_text)
            report.conflict_rate = self._conflict_rate(sample)

        return report

    def _compression_rate(self, nodes: list[MemoryNode], source_tokens: int | None) -> float:
        """Ratio of memory corpus tokens to source tokens."""
        if not source_tokens or source_tokens == 0:
            return 0.0
        memory_tokens = sum(len(n.content.split()) for n in nodes)
        return memory_tokens / source_tokens

    def _redundancy_rate(self, nodes: list[MemoryNode]) -> float:
        """Fraction of node pairs that are semantically redundant."""
        if len(nodes) < 2:
            return 0.0

        if self.embedding_provider:
            return self._redundancy_via_embeddings(nodes)
        return self._redundancy_via_overlap(nodes)

    def _redundancy_via_overlap(self, nodes: list[MemoryNode]) -> float:
        """Simple word-overlap redundancy (no embeddings)."""
        redundant_pairs = 0
        total_pairs = 0

        for i in range(min(len(nodes), 30)):
            words_i = set(nodes[i].content.lower().split())
            for j in range(i + 1, min(len(nodes), 30)):
                words_j = set(nodes[j].content.lower().split())
                total_pairs += 1
                overlap = len(words_i & words_j)
                union = len(words_i | words_j)
                if union > 0 and overlap / union > 0.7:
                    redundant_pairs += 1

        return redundant_pairs / total_pairs if total_pairs > 0 else 0.0

    def _redundancy_via_embeddings(self, nodes: list[MemoryNode]) -> float:
        """Cosine similarity-based redundancy detection."""
        from agent_memory_fabric.read.embeddings import cosine_similarity

        texts = [n.content for n in nodes[:30]]
        embeddings = self.embedding_provider.embed_batch(texts)

        redundant_pairs = 0
        total_pairs = 0
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                total_pairs += 1
                sim = cosine_similarity(embeddings[i], embeddings[j])
                if sim > 0.85:
                    redundant_pairs += 1

        return redundant_pairs / total_pairs if total_pairs > 0 else 0.0

    def _faithfulness(self, nodes: list[MemoryNode], source_text: str) -> float:
        """LLM-as-judge: fraction of memories grounded in source."""
        import json
        faithful_count = 0
        evaluated = 0

        for node in nodes[:20]:
            try:
                user_prompt = _FAITHFULNESS_USER.format(
                    source=source_text[:3000],
                    memory=node.content,
                )
                response = self.llm_provider.complete(_FAITHFULNESS_SYSTEM, user_prompt)
                data = json.loads(response.strip())
                if data.get("faithful"):
                    faithful_count += 1
                evaluated += 1
            except Exception:
                continue

        return faithful_count / evaluated if evaluated > 0 else 0.0

    def _conflict_rate(self, nodes: list[MemoryNode]) -> float:
        """LLM-as-judge: fraction of pairs with factual contradictions."""
        import json
        import random

        if len(nodes) < 2:
            return 0.0

        pairs = []
        indices = list(range(len(nodes)))
        random.shuffle(indices)
        for i in range(min(15, len(indices) - 1)):
            pairs.append((indices[i], indices[i + 1]))

        conflicts = 0
        evaluated = 0

        for i, j in pairs:
            try:
                user_prompt = _CONFLICT_USER.format(
                    memory_a=nodes[i].content,
                    memory_b=nodes[j].content,
                )
                response = self.llm_provider.complete(_CONFLICT_SYSTEM, user_prompt)
                data = json.loads(response.strip())
                if data.get("conflict"):
                    conflicts += 1
                evaluated += 1
            except Exception:
                continue

        return conflicts / evaluated if evaluated > 0 else 0.0
