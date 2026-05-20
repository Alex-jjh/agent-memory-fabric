#!/usr/bin/env python3
"""CLI entry point for running Paper 1 experiments.

Usage:
    # Run with synthetic data (for testing the harness)
    python -m benchmarks.run_experiment --synthetic

    # Run with LoCoMo data
    python -m benchmarks.run_experiment --data benchmarks/data/locomo-raw/data/test.json

    # Custom configuration
    python -m benchmarks.run_experiment --synthetic --top-k 10 --sessions 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmarks.conditions import (
    ContinuousDecayCondition,
    ExperimentCondition,
    FlatMemoryCondition,
    LifecycleCondition,
)
from benchmarks.harness import (
    ConversationSession,
    EvalQuestion,
    ExperimentConfig,
    ExperimentHarness,
    run_all_conditions,
)


def generate_synthetic_data(
    num_sessions: int = 5,
    turns_per_session: int = 10,
    num_questions: int = 20,
) -> tuple[list[ConversationSession], list[EvalQuestion]]:
    """Generate synthetic conversations + questions for harness testing.

    Creates a scenario where:
    - Early sessions contain facts that become stale (user moves cities, changes jobs)
    - Later sessions contain updated facts
    - Questions test whether the system returns current facts, not stale ones
    """
    sessions = []
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Session 1: User profile (some facts will become stale)
    sessions.append(ConversationSession(
        session_id="s1",
        timestamp=base_time,
        turns=[
            {"speaker": "User", "utterance": "I live in Shanghai and work at Amazon as a software engineer.", "dia_id": "D1:1"},
            {"speaker": "Assistant", "utterance": "Got it! You're based in Shanghai working at Amazon as a software engineer.", "dia_id": "D1:2"},
            {"speaker": "User", "utterance": "I'm studying for the AWS SAA certification exam next month.", "dia_id": "D1:3"},
            {"speaker": "Assistant", "utterance": "Good luck with your AWS Solutions Architect exam!", "dia_id": "D1:4"},
            {"speaker": "User", "utterance": "My favorite programming language is Python, I use it for everything.", "dia_id": "D1:5"},
        ],
    ))

    # Session 2: Project discussion
    sessions.append(ConversationSession(
        session_id="s2",
        timestamp=base_time + timedelta(days=7),
        turns=[
            {"speaker": "User", "utterance": "I'm working on a memory system project called Agent Memory Fabric.", "dia_id": "D2:1"},
            {"speaker": "Assistant", "utterance": "Tell me more about Agent Memory Fabric.", "dia_id": "D2:2"},
            {"speaker": "User", "utterance": "It uses a lifecycle state machine with four states: Active, Decided, Archived, Expired.", "dia_id": "D2:3"},
            {"speaker": "Assistant", "utterance": "Interesting architecture! The four-state lifecycle model sounds well-designed.", "dia_id": "D2:4"},
            {"speaker": "User", "utterance": "My supervisor Brennan is guiding the research direction for my FYP.", "dia_id": "D2:5"},
        ],
    ))

    # Session 3: Facts change (staleness source)
    sessions.append(ConversationSession(
        session_id="s3",
        timestamp=base_time + timedelta(days=30),
        turns=[
            {"speaker": "User", "utterance": "I moved to Suzhou last week, no longer in Shanghai.", "dia_id": "D3:1"},
            {"speaker": "Assistant", "utterance": "Noted, you've relocated from Shanghai to Suzhou.", "dia_id": "D3:2"},
            {"speaker": "User", "utterance": "I passed my AWS SAA exam! Got certified last Tuesday.", "dia_id": "D3:3"},
            {"speaker": "Assistant", "utterance": "Congratulations on passing the AWS SAA certification!", "dia_id": "D3:4"},
            {"speaker": "User", "utterance": "Now I'm preparing for the GRE exam for graduate school applications.", "dia_id": "D3:5"},
        ],
    ))

    # Session 4: More updates
    sessions.append(ConversationSession(
        session_id="s4",
        timestamp=base_time + timedelta(days=60),
        turns=[
            {"speaker": "User", "utterance": "I decided to target CHI 2027 LBW for my first paper submission.", "dia_id": "D4:1"},
            {"speaker": "Assistant", "utterance": "CHI 2027 Late-Breaking Work is a great venue for your lifecycle paper.", "dia_id": "D4:2"},
            {"speaker": "User", "utterance": "The Paper 1 baseline will be a Claude Code clone with proactive retrieval.", "dia_id": "D4:3"},
            {"speaker": "Assistant", "utterance": "Strong baseline choice — testing lifecycle on top of an already-good system.", "dia_id": "D4:4"},
            {"speaker": "User", "utterance": "I also started using TypeScript for the Obsidian plugin part of AMF.", "dia_id": "D4:5"},
        ],
    ))

    # Session 5: Latest state
    sessions.append(ConversationSession(
        session_id="s5",
        timestamp=base_time + timedelta(days=90),
        turns=[
            {"speaker": "User", "utterance": "My GRE exam is scheduled for next month, still preparing.", "dia_id": "D5:1"},
            {"speaker": "Assistant", "utterance": "Good luck with your upcoming GRE!", "dia_id": "D5:2"},
            {"speaker": "User", "utterance": "AMF now has 211 passing tests across all modules.", "dia_id": "D5:3"},
            {"speaker": "Assistant", "utterance": "Great test coverage for the project!", "dia_id": "D5:4"},
            {"speaker": "User", "utterance": "Brennan approved the three-condition experimental design for Paper 1.", "dia_id": "D5:5"},
        ],
    ))

    # Limit to requested number
    sessions = sessions[:num_sessions]

    # Questions that test staleness detection
    questions = [
        EvalQuestion(
            question="Where does the user currently live?",
            gold_answer="Suzhou",
            category="temporal_update",
            evidence_turns=["D3:1"],
        ),
        EvalQuestion(
            question="What city did the user previously live in?",
            gold_answer="Shanghai",
            category="historical",
            evidence_turns=["D1:1"],
        ),
        EvalQuestion(
            question="Has the user passed the AWS SAA exam?",
            gold_answer="yes",
            category="temporal_update",
            evidence_turns=["D3:3"],
        ),
        EvalQuestion(
            question="What is the user's current exam focus?",
            gold_answer="GRE",
            category="temporal_update",
            evidence_turns=["D3:5"],
        ),
        EvalQuestion(
            question="What are the four lifecycle states in AMF?",
            gold_answer="Active, Decided, Archived, Expired",
            category="factual",
            evidence_turns=["D2:3"],
        ),
        EvalQuestion(
            question="Who is the user's FYP supervisor?",
            gold_answer="Brennan",
            category="factual",
            evidence_turns=["D2:5"],
        ),
        EvalQuestion(
            question="What venue is Paper 1 targeting?",
            gold_answer="CHI 2027 LBW",
            category="factual",
            evidence_turns=["D4:1"],
        ),
        EvalQuestion(
            question="What is the Paper 1 baseline?",
            gold_answer="Claude Code clone",
            category="factual",
            evidence_turns=["D4:3"],
        ),
        EvalQuestion(
            question="What programming language does the user prefer?",
            gold_answer="Python",
            category="preference",
            evidence_turns=["D1:5"],
        ),
        EvalQuestion(
            question="Is the user still studying for AWS SAA?",
            gold_answer="no",
            category="temporal_update",
            evidence_turns=["D3:3"],
        ),
    ]

    return sessions, questions[:num_questions]


LOCOMO_CATEGORIES = {
    1: "single_hop",
    2: "temporal",
    3: "open_ended",
    4: "multi_hop",
    5: "knowledge_update",
}


def load_locomo_data(
    data_path: Path, max_entries: int | None = None
) -> tuple[list[ConversationSession], list[EvalQuestion]]:
    """Load LoCoMo dataset from JSON file.

    LoCoMo format:
    - Each entry has a 'conversation' dict with session_1..session_N (lists of turns)
    - Each turn: {"speaker": "Name", "dia_id": "D1:1", "text": "..."}
    - QA pairs: {"question": "...", "answer": "...", "evidence": ["D1:3"], "category": 1-5}
    """
    with open(data_path) as f:
        data = json.load(f)

    if max_entries:
        data = data[:max_entries]

    sessions = []
    questions = []

    for entry_idx, entry in enumerate(data):
        conversation = entry.get("conversation", {})

        # Extract session keys (session_1, session_2, ...) in order
        session_keys = sorted(
            [k for k in conversation.keys() if k.startswith("session_") and not k.endswith("date_time")],
            key=lambda x: int(x.split("_")[1]),
        )

        for sess_key in session_keys:
            turns = conversation[sess_key]
            formatted_turns = []
            for turn in turns:
                formatted_turns.append({
                    "speaker": turn.get("speaker", "Unknown"),
                    "utterance": turn.get("text", ""),
                    "dia_id": turn.get("dia_id", ""),
                })

            session_id = f"entry{entry_idx}_{sess_key}"

            sessions.append(ConversationSession(
                session_id=session_id,
                turns=formatted_turns,
            ))

        # Load QA pairs
        for qa in entry.get("qa", []):
            cat_id = qa.get("category", 0)
            category_name = LOCOMO_CATEGORIES.get(cat_id, f"cat_{cat_id}")
            gold = qa.get("answer", "") or qa.get("adversarial_answer", "")
            questions.append(EvalQuestion(
                question=qa.get("question", ""),
                gold_answer=str(gold),
                category=category_name,
                evidence_turns=qa.get("evidence", []),
            ))

    return sessions, questions


def main():
    parser = argparse.ArgumentParser(description="Run Paper 1 benchmark experiments")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic test data")
    parser.add_argument("--data", type=Path, help="Path to LoCoMo JSON file")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results"), help="Output directory")
    parser.add_argument("--top-k", type=int, default=5, help="Number of memories to retrieve")
    parser.add_argument("--sessions", type=int, default=5, help="Number of sessions (synthetic mode)")
    parser.add_argument("--questions", type=int, default=10, help="Number of questions (synthetic mode)")
    parser.add_argument("--max-entries", type=int, default=None, help="Limit LoCoMo entries (for quick testing)")
    parser.add_argument("--provider", choices=["mock", "bedrock"], default="mock", help="LLM provider for semantic condition")
    parser.add_argument("--time-gap", type=float, default=72.0, help="Hours between sessions (time simulation)")
    args = parser.parse_args()

    if not args.synthetic and not args.data:
        print("Error: specify --synthetic or --data <path>")
        sys.exit(1)

    if args.synthetic:
        print("Generating synthetic data...")
        sessions, questions = generate_synthetic_data(
            num_sessions=args.sessions,
            num_questions=args.questions,
        )
    else:
        print(f"Loading data from {args.data}...")
        sessions, questions = load_locomo_data(args.data, max_entries=args.max_entries)

    print(f"Sessions: {len(sessions)}, Questions: {len(questions)}")

    # Select LLM provider
    llm_provider = None
    if args.provider == "bedrock":
        from agent_memory_fabric.llm.provider import BedrockProvider
        llm_provider = BedrockProvider()
        print(f"LLM Provider: Bedrock ({llm_provider.model_id})")
    else:
        print("LLM Provider: Mock (semantic condition uses default NO)")

    config = ExperimentConfig(top_k=args.top_k, time_gap_between_sessions_hours=args.time_gap)
    results = run_all_conditions(sessions, questions, args.output, config, llm_provider=llm_provider)

    # Print comparison table
    cond_names = ["flat", "continuous_decay", "lifecycle", "semantic_lifecycle"]
    print(f"\n{'='*76}")
    print("COMPARISON TABLE (Overall)")
    print(f"{'='*76}")
    print(f"{'Metric':<25} {'Flat':<13} {'Decay':<13} {'Lifecycle':<13} {'Semantic':<13}")
    print("-" * 77)
    for metric in ["qa_accuracy", "memory_size", "staleness_intrusion_rate", "precision@5"]:
        row = f"{metric:<25}"
        for cond_name in cond_names:
            if cond_name in results:
                val = results[cond_name].to_dict().get(metric, "N/A")
                row += f" {str(val):<13}"
        print(row)

    # Per-category QA accuracy
    all_cats = set()
    for m in results.values():
        all_cats.update(m.per_category.keys())
    if all_cats:
        print(f"\n{'='*76}")
        print("PER-CATEGORY QA ACCURACY")
        print(f"{'='*76}")
        print(f"{'Category':<25} {'Flat':<13} {'Decay':<13} {'Lifecycle':<13} {'Semantic':<13}")
        print("-" * 77)
        for cat in sorted(all_cats):
            row = f"{cat:<25}"
            for cond_name in cond_names:
                if cond_name in results:
                    cat_data = results[cond_name].per_category.get(cat, {})
                    qa = cat_data.get("qa_accuracy", "N/A")
                    n = cat_data.get("count", 0)
                    row += f" {qa} (n={n})  " if isinstance(qa, float) else f" {'N/A':<13}"
                else:
                    row += f" {'N/A':<13}"
            print(row)

    # State distribution for lifecycle conditions
    print(f"\n{'='*76}")
    print("MEMORY STATE DISTRIBUTION")
    print(f"{'='*76}")


if __name__ == "__main__":
    main()
