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
            {"speaker": "User", "utterance": "I live in Shanghai and work at Amazon as a software engineer."},
            {"speaker": "Assistant", "utterance": "Got it! You're based in Shanghai working at Amazon as a software engineer."},
            {"speaker": "User", "utterance": "I'm studying for the AWS SAA certification exam next month."},
            {"speaker": "Assistant", "utterance": "Good luck with your AWS Solutions Architect exam!"},
            {"speaker": "User", "utterance": "My favorite programming language is Python, I use it for everything."},
        ],
    ))

    # Session 2: Project discussion
    sessions.append(ConversationSession(
        session_id="s2",
        timestamp=base_time + timedelta(days=7),
        turns=[
            {"speaker": "User", "utterance": "I'm working on a memory system project called Agent Memory Fabric."},
            {"speaker": "Assistant", "utterance": "Tell me more about Agent Memory Fabric."},
            {"speaker": "User", "utterance": "It uses a lifecycle state machine with four states: Active, Decided, Archived, Expired."},
            {"speaker": "Assistant", "utterance": "Interesting architecture! The four-state lifecycle model sounds well-designed."},
            {"speaker": "User", "utterance": "My supervisor Brennan is guiding the research direction for my FYP."},
        ],
    ))

    # Session 3: Facts change (staleness source)
    sessions.append(ConversationSession(
        session_id="s3",
        timestamp=base_time + timedelta(days=30),
        turns=[
            {"speaker": "User", "utterance": "I moved to Suzhou last week, no longer in Shanghai."},
            {"speaker": "Assistant", "utterance": "Noted, you've relocated from Shanghai to Suzhou."},
            {"speaker": "User", "utterance": "I passed my AWS SAA exam! Got certified last Tuesday."},
            {"speaker": "Assistant", "utterance": "Congratulations on passing the AWS SAA certification!"},
            {"speaker": "User", "utterance": "Now I'm preparing for the GRE exam for graduate school applications."},
        ],
    ))

    # Session 4: More updates
    sessions.append(ConversationSession(
        session_id="s4",
        timestamp=base_time + timedelta(days=60),
        turns=[
            {"speaker": "User", "utterance": "I decided to target CHI 2027 LBW for my first paper submission."},
            {"speaker": "Assistant", "utterance": "CHI 2027 Late-Breaking Work is a great venue for your lifecycle paper."},
            {"speaker": "User", "utterance": "The Paper 1 baseline will be a Claude Code clone with proactive retrieval."},
            {"speaker": "Assistant", "utterance": "Strong baseline choice — testing lifecycle on top of an already-good system."},
            {"speaker": "User", "utterance": "I also started using TypeScript for the Obsidian plugin part of AMF."},
        ],
    ))

    # Session 5: Latest state
    sessions.append(ConversationSession(
        session_id="s5",
        timestamp=base_time + timedelta(days=90),
        turns=[
            {"speaker": "User", "utterance": "My GRE exam is scheduled for next month, still preparing."},
            {"speaker": "Assistant", "utterance": "Good luck with your upcoming GRE!"},
            {"speaker": "User", "utterance": "AMF now has 211 passing tests across all modules."},
            {"speaker": "Assistant", "utterance": "Great test coverage for the project!"},
            {"speaker": "User", "utterance": "Brennan approved the three-condition experimental design for Paper 1."},
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
            evidence_turns=["I moved to Suzhou last week"],
        ),
        EvalQuestion(
            question="What city did the user previously live in?",
            gold_answer="Shanghai",
            category="historical",
            evidence_turns=["I live in Shanghai"],
        ),
        EvalQuestion(
            question="Has the user passed the AWS SAA exam?",
            gold_answer="yes",
            category="temporal_update",
            evidence_turns=["I passed my AWS SAA exam"],
        ),
        EvalQuestion(
            question="What is the user's current exam focus?",
            gold_answer="GRE",
            category="temporal_update",
            evidence_turns=["I'm preparing for the GRE exam"],
        ),
        EvalQuestion(
            question="What are the four lifecycle states in AMF?",
            gold_answer="Active, Decided, Archived, Expired",
            category="factual",
            evidence_turns=["four states: Active, Decided, Archived, Expired"],
        ),
        EvalQuestion(
            question="Who is the user's FYP supervisor?",
            gold_answer="Brennan",
            category="factual",
            evidence_turns=["My supervisor Brennan"],
        ),
        EvalQuestion(
            question="What venue is Paper 1 targeting?",
            gold_answer="CHI 2027 LBW",
            category="factual",
            evidence_turns=["target CHI 2027 LBW"],
        ),
        EvalQuestion(
            question="What is the Paper 1 baseline?",
            gold_answer="Claude Code clone",
            category="factual",
            evidence_turns=["baseline will be a Claude Code clone"],
        ),
        EvalQuestion(
            question="What programming language does the user prefer?",
            gold_answer="Python",
            category="preference",
            evidence_turns=["favorite programming language is Python"],
        ),
        EvalQuestion(
            question="Is the user still studying for AWS SAA?",
            gold_answer="no",
            category="temporal_update",
            evidence_turns=["I passed my AWS SAA exam"],
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
                })

            session_id = f"entry{entry_idx}_{sess_key}"
            date_key = f"{sess_key}_date_time"
            timestamp_str = conversation.get(date_key, "")

            sessions.append(ConversationSession(
                session_id=session_id,
                turns=formatted_turns,
            ))

        # Load QA pairs
        for qa in entry.get("qa", []):
            cat_id = qa.get("category", 0)
            category_name = LOCOMO_CATEGORIES.get(cat_id, f"cat_{cat_id}")
            questions.append(EvalQuestion(
                question=qa.get("question", ""),
                gold_answer=qa.get("answer", ""),
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

    config = ExperimentConfig(top_k=args.top_k)
    results = run_all_conditions(sessions, questions, args.output, config)

    # Print comparison table
    print(f"\n{'='*60}")
    print("COMPARISON TABLE")
    print(f"{'='*60}")
    print(f"{'Metric':<25} {'Flat':<12} {'Decay':<12} {'Lifecycle':<12}")
    print("-" * 61)
    for metric in ["precision@5", "staleness_intrusion_rate", "qa_accuracy", "memory_size"]:
        row = f"{metric:<25}"
        for cond_name in ["flat", "continuous_decay", "lifecycle"]:
            if cond_name in results:
                val = results[cond_name].to_dict().get(metric, "N/A")
                row += f" {val:<12}"
        print(row)


if __name__ == "__main__":
    main()
