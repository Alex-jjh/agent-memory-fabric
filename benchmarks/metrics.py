"""Evaluation metrics for Paper 1 experiments.

Metrics:
- Precision@K: fraction of top-K retrieved memories that are relevant
- QA Accuracy: whether the retrieved context supports answering the question correctly
- Staleness Intrusion Rate (SIR): fraction of retrieved memories that are stale/outdated
- Memory Size: total memory corpus size (measures accumulation)
- Token Efficiency: useful tokens / total injected tokens
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent_memory_fabric.core.node import MemoryNode


@dataclass
class RetrievalResult:
    """Result of a single retrieval query."""
    query: str
    retrieved: list[MemoryNode]
    gold_answer: Optional[str] = None
    gold_evidence: list[str] = field(default_factory=list)
    category: str = "unknown"


@dataclass
class MetricValues:
    """Computed metrics for a single query."""
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    staleness_intrusion_rate: float = 0.0
    has_correct_answer: bool = False
    retrieved_count: int = 0
    relevant_count: int = 0


def precision_at_k(retrieved: list[MemoryNode], relevant_ids: set[str], k: int = 5) -> float:
    """Fraction of top-K results that are relevant."""
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    relevant_in_top_k = sum(1 for n in top_k if n.id in relevant_ids)
    return relevant_in_top_k / len(top_k)


def recall_at_k(retrieved: list[MemoryNode], relevant_ids: set[str], k: int = 5) -> float:
    """Fraction of relevant items that appear in top-K results."""
    if not relevant_ids:
        return 0.0
    top_k = retrieved[:k]
    found = sum(1 for n in top_k if n.id in relevant_ids)
    return found / len(relevant_ids)


def staleness_intrusion_rate(
    retrieved: list[MemoryNode],
    stale_node_ids: set[str],
    k: int = 5,
) -> float:
    """Fraction of top-K results that are known-stale (should have been excluded).

    This is the key metric for Paper 1: lifecycle should reduce SIR to near-zero
    because stale memories are architecturally excluded (Archived/Expired state),
    while flat/decay conditions will have non-zero SIR.
    """
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    stale_in_top_k = sum(1 for n in top_k if n.id in stale_node_ids)
    return stale_in_top_k / len(top_k)


def _normalize_tokens(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into tokens."""
    import re
    return re.findall(r"\w+", text.lower())


def token_f1(prediction_text: str, gold_answer: str) -> float:
    """Compute token-level F1 between a prediction text and gold answer."""
    pred_tokens = _normalize_tokens(prediction_text)
    gold_tokens = _normalize_tokens(gold_answer)
    if not gold_tokens or not pred_tokens:
        return 0.0
    common = set(pred_tokens) & set(gold_tokens)
    if not common:
        return 0.0
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def token_recall(context_text: str, gold_answer: str) -> float:
    """Fraction of gold answer tokens present in the context text.

    This is the right metric for retrieval QA: does the retrieved context
    contain the information needed to answer? We don't penalize extra tokens
    in the context (that's what precision@k is for).
    """
    context_tokens = set(_normalize_tokens(context_text))
    gold_tokens = _normalize_tokens(gold_answer)
    if not gold_tokens:
        return 0.0
    found = sum(1 for t in gold_tokens if t in context_tokens)
    return found / len(gold_tokens)


def qa_accuracy(retrieved: list[MemoryNode], gold_answer: str | None, threshold: float = 0.8) -> bool:
    """Check if any retrieved memory contains enough of the gold answer to support it.

    Uses token recall: what fraction of gold answer tokens appear in the retrieved text.
    Threshold 0.8 means at least 80% of gold tokens must be present.
    """
    if gold_answer is None:
        return False
    gold = str(gold_answer).strip()
    if not gold:
        return False
    for node in retrieved:
        if token_recall(node.content, gold) >= threshold:
            return True
    return False


def token_efficiency(retrieved: list[MemoryNode], relevant_ids: set[str]) -> float:
    """Ratio of relevant content tokens to total injected tokens.

    Higher = less noise injected per useful piece of information.
    """
    total_tokens = sum(len(n.content.split()) for n in retrieved)
    relevant_tokens = sum(len(n.content.split()) for n in retrieved if n.id in relevant_ids)
    if total_tokens == 0:
        return 0.0
    return relevant_tokens / total_tokens


def memory_corpus_size(engine) -> int:
    """Number of searchable memory nodes (active + decided, excludes archived/expired)."""
    active = len(engine.list_nodes(state="active"))
    decided = len(engine.list_nodes(state="decided"))
    return active + decided


@dataclass
class ExperimentMetrics:
    """Aggregated metrics across all queries in an experiment."""
    condition_name: str
    num_queries: int = 0
    mean_precision_at_5: float = 0.0
    mean_recall_at_5: float = 0.0
    mean_sir: float = 0.0
    qa_accuracy: float = 0.0
    mean_token_efficiency: float = 0.0
    final_memory_size: int = 0
    per_category: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "condition": self.condition_name,
            "num_queries": self.num_queries,
            "precision@5": round(self.mean_precision_at_5, 4),
            "recall@5": round(self.mean_recall_at_5, 4),
            "staleness_intrusion_rate": round(self.mean_sir, 4),
            "qa_accuracy": round(self.qa_accuracy, 4),
            "token_efficiency": round(self.mean_token_efficiency, 4),
            "memory_size": self.final_memory_size,
            "per_category": self.per_category,
        }
