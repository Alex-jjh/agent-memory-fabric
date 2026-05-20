"""Experiment harness — runs the three-condition Paper 1 ablation.

Protocol:
1. For each condition (flat, decay, lifecycle):
   a. Create a fresh MemoryEngine
   b. Ingest all conversation sessions sequentially
   c. After each session, run condition-specific after_session() (decay/transitions)
   d. For each question, query the memory system (top_k=5)
   e. Compute metrics against gold answers/evidence

This simulates a real-world extended conversation where memories accumulate
and some become stale over time.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.node import MemoryNode

from benchmarks.conditions import ExperimentCondition
from benchmarks.metrics import (
    ExperimentMetrics,
    memory_corpus_size,
    precision_at_k,
    qa_accuracy_exact,
    recall_at_k,
    staleness_intrusion_rate,
    token_efficiency,
)


@dataclass
class ConversationSession:
    """A conversation session from the dataset."""
    session_id: str
    turns: list[dict]  # [{"speaker": "...", "utterance": "..."}]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EvalQuestion:
    """An evaluation question with gold answer and evidence."""
    question: str
    gold_answer: str
    evidence_turns: list[str] = field(default_factory=list)
    category: str = "unknown"
    relevant_memory_ids: set[str] = field(default_factory=set)
    stale_memory_ids: set[str] = field(default_factory=set)


@dataclass
class ExperimentConfig:
    """Configuration for an experiment run."""
    top_k: int = 5
    sessions_before_eval: int | None = None  # None = ingest all, then eval all
    time_gap_between_sessions_hours: float = 24.0  # simulate time passing
    max_memories_per_turn: int = 3


class ExperimentHarness:
    """Runs a single experimental condition and computes metrics."""

    def __init__(
        self,
        condition: ExperimentCondition,
        vault_path: Path,
        config: ExperimentConfig | None = None,
    ):
        self.condition = condition
        self.vault_path = vault_path
        self.config = config or ExperimentConfig()
        self.engine = condition.create_engine(vault_path)
        self._ingested_ids: list[str] = []
        self._stale_ids: set[str] = set()

    def ingest_session(self, session: ConversationSession) -> list[str]:
        """Ingest a conversation session into memory. Returns IDs of created nodes."""
        from benchmarks.conditions import SemanticLifecycleCondition

        created_ids = []

        for turn in session.turns:
            speaker = turn.get("speaker", "unknown")
            utterance = turn.get("utterance", "")

            if not utterance.strip() or len(utterance.split()) < 5:
                continue

            content = f"[{speaker}] {utterance}"

            # Semantic condition: check contradictions before writing
            if isinstance(self.condition, SemanticLifecycleCondition):
                self.condition.ingest_with_contradiction_check(self.engine, content)

            node = self.engine.write(
                content=content,
                name=None,
                tags=[f"session:{session.session_id}", f"speaker:{speaker}"],
            )
            if node is not None:
                created_ids.append(node.id)

        self._ingested_ids.extend(created_ids)
        self.condition.after_session(self.engine)
        return created_ids

    def mark_stale(self, node_ids: set[str]) -> None:
        """Mark specific memories as stale (for SIR computation).

        In a real experiment, staleness is determined by temporal ordering:
        memories about facts that were later contradicted or superseded.
        """
        self._stale_ids.update(node_ids)

    def evaluate_question(self, question: EvalQuestion) -> dict:
        """Retrieve memories for a question and compute metrics."""
        retrieved = self.condition.search(
            self.engine, question.question, top_k=self.config.top_k
        )

        relevant_ids = question.relevant_memory_ids or set()
        stale_ids = question.stale_memory_ids or self._stale_ids

        p_at_k = precision_at_k(retrieved, relevant_ids, self.config.top_k)
        r_at_k = recall_at_k(retrieved, relevant_ids, self.config.top_k)
        sir = staleness_intrusion_rate(retrieved, stale_ids, self.config.top_k)
        qa_correct = qa_accuracy_exact(retrieved, question.gold_answer)
        tok_eff = token_efficiency(retrieved, relevant_ids)

        return {
            "question": question.question,
            "category": question.category,
            "precision@k": p_at_k,
            "recall@k": r_at_k,
            "sir": sir,
            "qa_correct": qa_correct,
            "token_efficiency": tok_eff,
            "num_retrieved": len(retrieved),
        }

    def run_full_experiment(
        self,
        sessions: list[ConversationSession],
        questions: list[EvalQuestion],
        simulate_time_gap: bool = True,
    ) -> ExperimentMetrics:
        """Run the complete experiment: ingest all sessions, then evaluate all questions.

        If simulate_time_gap=True, artificially ages memories between sessions
        by backdating their last_accessed times to simulate temporal spread.
        """
        # Phase 1: Ingest with simulated time gaps
        for i, session in enumerate(sessions):
            ids = self.ingest_session(session)

            if simulate_time_gap and ids:
                days_ago = (len(sessions) - i) * self.config.time_gap_between_sessions_hours / 24
                self._backdate_memories(ids, days_ago)

            self.condition.after_session(self.engine)

        # Phase 2: Evaluate
        results = []
        for q in questions:
            result = self.evaluate_question(q)
            results.append(result)

        # Phase 3: Aggregate
        return self._aggregate_metrics(results)

    def _backdate_memories(self, node_ids: list[str], days_ago: float) -> None:
        """Artificially age memories to simulate time passing between sessions."""
        from datetime import timedelta
        delta = timedelta(days=days_ago)
        for node_id in node_ids:
            node = self.engine.read(node_id)
            if node:
                node.last_accessed = node.last_accessed - delta
                node.created = node.created - delta
                node.modified = node.modified - delta
                self.engine.markdown_store.write(node)
                self.engine.sqlite_store.upsert_node(node, content=node.content)

    def _aggregate_metrics(self, results: list[dict]) -> ExperimentMetrics:
        """Aggregate per-query results into experiment-level metrics."""
        if not results:
            return ExperimentMetrics(condition_name=self.condition.name)

        n = len(results)
        mean_p = sum(r["precision@k"] for r in results) / n
        mean_r = sum(r["recall@k"] for r in results) / n
        mean_sir = sum(r["sir"] for r in results) / n
        qa_acc = sum(1 for r in results if r["qa_correct"]) / n
        mean_tok = sum(r["token_efficiency"] for r in results) / n

        # Per-category breakdown
        categories: dict[str, list[dict]] = {}
        for r in results:
            cat = r["category"]
            categories.setdefault(cat, []).append(r)

        per_category = {}
        for cat, cat_results in categories.items():
            cn = len(cat_results)
            per_category[cat] = {
                "precision@5": round(sum(r["precision@k"] for r in cat_results) / cn, 4),
                "recall@5": round(sum(r["recall@k"] for r in cat_results) / cn, 4),
                "sir": round(sum(r["sir"] for r in cat_results) / cn, 4),
                "qa_accuracy": round(sum(1 for r in cat_results if r["qa_correct"]) / cn, 4),
                "count": cn,
            }

        return ExperimentMetrics(
            condition_name=self.condition.name,
            num_queries=n,
            mean_precision_at_5=mean_p,
            mean_recall_at_5=mean_r,
            mean_sir=mean_sir,
            qa_accuracy=qa_acc,
            mean_token_efficiency=mean_tok,
            final_memory_size=memory_corpus_size(self.engine),
            per_category=per_category,
        )


def run_all_conditions(
    sessions: list[ConversationSession],
    questions: list[EvalQuestion],
    output_dir: Path,
    config: ExperimentConfig | None = None,
) -> dict[str, ExperimentMetrics]:
    """Run all three conditions and save results."""
    from benchmarks.conditions import (
        ContinuousDecayCondition,
        FlatMemoryCondition,
        LifecycleCondition,
        SemanticLifecycleCondition,
    )

    conditions = [
        FlatMemoryCondition(),
        ContinuousDecayCondition(),
        LifecycleCondition(),
        SemanticLifecycleCondition(),
    ]

    all_results = {}
    output_dir.mkdir(parents=True, exist_ok=True)

    for condition in conditions:
        print(f"\n{'='*60}")
        print(f"Running condition: {condition.name}")
        print(f"{'='*60}")

        vault_path = output_dir / f"vault_{condition.name}"
        harness = ExperimentHarness(condition, vault_path, config)

        start = time.time()
        metrics = harness.run_full_experiment(sessions, questions)
        elapsed = time.time() - start

        all_results[condition.name] = metrics

        print(f"  Completed in {elapsed:.1f}s")
        print(f"  Precision@5: {metrics.mean_precision_at_5:.4f}")
        print(f"  SIR: {metrics.mean_sir:.4f}")
        print(f"  QA Accuracy: {metrics.qa_accuracy:.4f}")
        print(f"  Memory Size: {metrics.final_memory_size}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = output_dir / f"results_{timestamp}.json"
    results_data = {name: m.to_dict() for name, m in all_results.items()}
    results_file.write_text(json.dumps(results_data, indent=2))
    print(f"\nResults saved to: {results_file}")

    return all_results
