#!/usr/bin/env python3
"""Run STALE contradiction detection evaluation.

Usage:
    python -m benchmarks.stale.run_stale              # Mock data + MockProvider
    python -m benchmarks.stale.run_stale --bedrock    # Mock data + real Bedrock LLM
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.llm.contradiction import detect_contradictions
from agent_memory_fabric.llm.provider import BedrockProvider, MockProvider

from benchmarks.stale.mock_stale import StalePair, generate_mock_stale_pairs


@dataclass
class TDAMetrics:
    """True Detection Accuracy metrics."""
    total: int = 0
    true_positives: int = 0   # correctly detected contradictions
    false_positives: int = 0  # incorrectly flagged non-contradictions
    true_negatives: int = 0   # correctly passed non-contradictions
    false_negatives: int = 0  # missed real contradictions

    @property
    def accuracy(self) -> float:
        return (self.true_positives + self.true_negatives) / self.total if self.total > 0 else 0.0

    @property
    def tpr(self) -> float:
        """True Positive Rate (sensitivity/recall)."""
        pos = self.true_positives + self.false_negatives
        return self.true_positives / pos if pos > 0 else 0.0

    @property
    def fpr(self) -> float:
        """False Positive Rate."""
        neg = self.false_positives + self.true_negatives
        return self.false_positives / neg if neg > 0 else 0.0

    @property
    def tnr(self) -> float:
        """True Negative Rate (specificity)."""
        return 1.0 - self.fpr

    @property
    def fnr(self) -> float:
        """False Negative Rate."""
        return 1.0 - self.tpr

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.tpr
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "accuracy": round(self.accuracy, 4),
            "tpr_sensitivity": round(self.tpr, 4),
            "fpr": round(self.fpr, 4),
            "tnr_specificity": round(self.tnr, 4),
            "fnr": round(self.fnr, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
        }


def evaluate_pairs(pairs: list[StalePair], provider) -> TDAMetrics:
    """Evaluate contradiction detection on STALE pairs."""
    metrics = TDAMetrics(total=len(pairs))

    for pair in pairs:
        existing_node = MemoryNode(name="existing", content=pair.old_memory)
        results = detect_contradictions(pair.new_information, [existing_node], provider)

        detected = len(results) > 0

        if pair.is_contradiction and detected:
            metrics.true_positives += 1
        elif pair.is_contradiction and not detected:
            metrics.false_negatives += 1
        elif not pair.is_contradiction and detected:
            metrics.false_positives += 1
        else:
            metrics.true_negatives += 1

    return metrics


def evaluate_by_category(pairs: list[StalePair], provider) -> dict[str, TDAMetrics]:
    """Evaluate per-category metrics."""
    categories: dict[str, list[StalePair]] = {}
    for pair in pairs:
        categories.setdefault(pair.category, []).append(pair)

    results = {}
    for cat, cat_pairs in categories.items():
        results[cat] = evaluate_pairs(cat_pairs, provider)
    return results


def main():
    parser = argparse.ArgumentParser(description="Run STALE contradiction detection evaluation")
    parser.add_argument("--bedrock", action="store_true", help="Use real Bedrock LLM (requires AWS creds)")
    parser.add_argument("--output", type=Path, default=None, help="Save results to JSON file")
    args = parser.parse_args()

    print("=" * 60)
    print("STALE Contradiction Detection Evaluation")
    print("=" * 60)

    # Load pairs
    pairs = generate_mock_stale_pairs()
    print(f"\nPairs: {len(pairs)} ({sum(1 for p in pairs if p.is_contradiction)} contradictions, "
          f"{sum(1 for p in pairs if not p.is_contradiction)} non-contradictions)")

    # Select provider
    if args.bedrock:
        print("Provider: AWS Bedrock (Claude)")
        provider = BedrockProvider()
    else:
        print("Provider: MockProvider (baseline — all NO)")
        provider = MockProvider(default_response="NO")

    # Overall evaluation
    print("\n--- Overall Metrics ---")
    overall = evaluate_pairs(pairs, provider)
    for key, val in overall.to_dict().items():
        print(f"  {key:<20}: {val}")

    # Per-category evaluation
    print("\n--- Per-Category Metrics ---")
    by_category = evaluate_by_category(pairs, provider)
    for cat, cat_metrics in sorted(by_category.items()):
        print(f"\n  [{cat}] (n={cat_metrics.total}):")
        print(f"    Accuracy: {cat_metrics.accuracy:.4f}  TPR: {cat_metrics.tpr:.4f}  FPR: {cat_metrics.fpr:.4f}")

    # Save results
    if args.output:
        result_data = {
            "overall": overall.to_dict(),
            "per_category": {cat: m.to_dict() for cat, m in by_category.items()},
            "provider": "bedrock" if args.bedrock else "mock",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result_data, indent=2))
        print(f"\nResults saved to: {args.output}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: Accuracy={overall.accuracy:.1%}  F1={overall.f1:.4f}  "
          f"TPR={overall.tpr:.1%}  FPR={overall.fpr:.1%}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
