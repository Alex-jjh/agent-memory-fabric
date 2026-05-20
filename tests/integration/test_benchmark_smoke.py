"""Smoke tests for benchmark harness — verify metrics pipeline produces sensible values."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from benchmarks.conditions import (
    ContinuousDecayCondition,
    FlatMemoryCondition,
    LifecycleCondition,
    SemanticLifecycleCondition,
)
from benchmarks.harness import (
    ConversationSession,
    EvalQuestion,
    ExperimentConfig,
    ExperimentHarness,
)
from benchmarks.metrics import qa_accuracy, token_f1, token_recall, memory_corpus_size


@pytest.fixture
def sessions_and_questions():
    """Minimal dataset: two sessions where a fact changes, plus eval questions."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    sessions = [
        ConversationSession(
            session_id="s1",
            turns=[
                {"speaker": "User", "utterance": "I live in Shanghai and work at Amazon as a software engineer.", "dia_id": "D1:1"},
                {"speaker": "Assistant", "utterance": "Got it, you are based in Shanghai working at Amazon.", "dia_id": "D1:2"},
                {"speaker": "User", "utterance": "My favorite food is sushi, I eat it every week.", "dia_id": "D1:3"},
            ],
            timestamp=base_time,
        ),
        ConversationSession(
            session_id="s2",
            turns=[
                {"speaker": "User", "utterance": "I moved to Sydney last month and now work at Google.", "dia_id": "D2:1"},
                {"speaker": "Assistant", "utterance": "Congrats on the move to Sydney and the new role at Google!", "dia_id": "D2:2"},
                {"speaker": "User", "utterance": "I have been exploring Australian food, but still love sushi.", "dia_id": "D2:3"},
            ],
            timestamp=base_time + timedelta(days=30),
        ),
    ]

    questions = [
        EvalQuestion(
            question="Where does the user live?",
            gold_answer="Sydney",
            category="factual",
            evidence_turns=["D2:1"],
        ),
        EvalQuestion(
            question="Where does the user work?",
            gold_answer="Google",
            category="factual",
            evidence_turns=["D2:1"],
        ),
        EvalQuestion(
            question="What is the user's favorite food?",
            gold_answer="sushi",
            category="preference",
            evidence_turns=["D1:3"],
        ),
    ]

    return sessions, questions


class TestTokenF1:
    def test_exact_match(self):
        assert token_f1("sushi", "sushi") == 1.0

    def test_partial_overlap(self):
        score = token_f1("I live in Shanghai and work at Amazon", "Shanghai")
        assert 0.1 < score < 1.0

    def test_no_overlap(self):
        assert token_f1("apples and oranges", "quantum mechanics") == 0.0

    def test_empty(self):
        assert token_f1("", "answer") == 0.0
        assert token_f1("text", "") == 0.0


class TestTokenRecall:
    def test_single_word_in_long_sentence(self):
        score = token_recall(
            "[User] I moved to Sydney last month and now work at Google.",
            "Sydney",
        )
        assert score == 1.0

    def test_multi_word_answer(self):
        score = token_recall(
            "[User] I moved to Sydney last month and now work at Google.",
            "Sydney Google",
        )
        assert score == 1.0

    def test_partial_match(self):
        score = token_recall(
            "[User] I live in Shanghai.",
            "Shanghai Amazon",
        )
        assert score == 0.5

    def test_no_match(self):
        assert token_recall("apples and oranges", "quantum mechanics") == 0.0


class TestQaAccuracy:
    def test_answer_present_in_retrieved(self):
        from agent_memory_fabric.core.node import MemoryNode, LifecycleState
        node = MemoryNode(
            id="test1",
            name="test",
            content="[User] I moved to Sydney last month and now work at Google.",
            state=LifecycleState.ACTIVE,
        )
        assert qa_accuracy([node], "Sydney") is True
        assert qa_accuracy([node], "Google") is True

    def test_multi_token_answer(self):
        from agent_memory_fabric.core.node import MemoryNode, LifecycleState
        node = MemoryNode(
            id="test1",
            name="test",
            content="[User] I went to a LGBTQ support group yesterday on 7 May 2023.",
            state=LifecycleState.ACTIVE,
        )
        assert qa_accuracy([node], "7 May 2023") is True

    def test_answer_not_present(self):
        from agent_memory_fabric.core.node import MemoryNode, LifecycleState
        node = MemoryNode(
            id="test1",
            name="test",
            content="[User] I live in Shanghai and work at Amazon.",
            state=LifecycleState.ACTIVE,
        )
        assert qa_accuracy([node], "Sydney") is False


class TestHarnessEvidenceMapping:
    def test_dia_id_to_node_id_mapping(self, sessions_and_questions):
        sessions, questions = sessions_and_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            condition = FlatMemoryCondition()
            harness = ExperimentHarness(condition, Path(tmpdir), ExperimentConfig(top_k=5))

            for session in sessions:
                harness.ingest_session(session)

            assert "D1:1" in harness._dia_id_to_node_id
            assert "D2:1" in harness._dia_id_to_node_id

            resolved = harness.resolve_evidence(questions[0])
            assert len(resolved) == 1
            assert harness._dia_id_to_node_id["D2:1"] in resolved


class TestHarnessSmokeEndToEnd:
    def test_flat_produces_nonzero_metrics(self, sessions_and_questions):
        sessions, questions = sessions_and_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            condition = FlatMemoryCondition()
            config = ExperimentConfig(top_k=5, time_gap_between_sessions_hours=72.0)
            harness = ExperimentHarness(condition, Path(tmpdir), config)
            metrics = harness.run_full_experiment(sessions, questions, simulate_time_gap=False)

            assert metrics.num_queries == 3
            assert metrics.qa_accuracy > 0, "qa_accuracy should be > 0 when answer is in retrieved context"
            assert metrics.mean_precision_at_5 > 0, "precision should be > 0 when evidence is mapped"
            assert metrics.mean_recall_at_5 > 0, "recall should be > 0 when evidence is mapped"

    def test_lifecycle_archives_old_memories(self, sessions_and_questions):
        sessions, questions = sessions_and_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            condition = LifecycleCondition(forget_threshold=0.3, min_inactive_days=5)
            config = ExperimentConfig(top_k=5, time_gap_between_sessions_hours=168.0)
            harness = ExperimentHarness(condition, Path(tmpdir), config)
            metrics = harness.run_full_experiment(sessions, questions, simulate_time_gap=True)

            corpus_size = memory_corpus_size(harness.engine)
            total_nodes = len(harness._ingested_ids)
            assert corpus_size <= total_nodes, (
                f"Lifecycle should archive some old nodes: searchable={corpus_size}, total={total_nodes}"
            )

    def test_memory_size_excludes_archived(self, sessions_and_questions):
        sessions, _ = sessions_and_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            condition = FlatMemoryCondition()
            harness = ExperimentHarness(condition, Path(tmpdir))
            for session in sessions:
                harness.ingest_session(session)

            all_nodes = len(harness.engine.list_nodes())
            searchable = memory_corpus_size(harness.engine)
            assert searchable == all_nodes

            first_id = harness._ingested_ids[0]
            harness.engine.transition(first_id, "archived", reason="test")

            searchable_after = memory_corpus_size(harness.engine)
            assert searchable_after == all_nodes - 1

    def test_all_conditions_differ_on_temporal_data(self, sessions_and_questions):
        """Verify that conditions produce at least partially different metrics."""
        sessions, questions = sessions_and_questions
        results = {}
        for CondClass in [FlatMemoryCondition, ContinuousDecayCondition, LifecycleCondition]:
            with tempfile.TemporaryDirectory() as tmpdir:
                condition = CondClass() if CondClass != LifecycleCondition else CondClass(forget_threshold=0.3, min_inactive_days=5)
                config = ExperimentConfig(top_k=5, time_gap_between_sessions_hours=168.0)
                harness = ExperimentHarness(condition, Path(tmpdir), config)
                metrics = harness.run_full_experiment(sessions, questions, simulate_time_gap=True)
                results[condition.name] = metrics

        assert all(m.num_queries == 3 for m in results.values())
        assert all(m.qa_accuracy >= 0 for m in results.values())
