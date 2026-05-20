"""Tests for abstain gate."""

from agent_memory_fabric.read.abstain import AbstainGate


class TestAbstainGate:
    def setup_method(self):
        self.gate = AbstainGate(min_words=3, score_threshold=0.15)

    def test_empty_message_abstains(self):
        assert self.gate.should_abstain("") is True
        assert self.gate.should_abstain("   ") is True

    def test_short_message_abstains(self):
        assert self.gate.should_abstain("ok") is True
        assert self.gate.should_abstain("hi there") is True

    def test_greeting_abstains(self):
        assert self.gate.should_abstain("hello how are you") is True
        assert self.gate.should_abstain("thanks for the help with that") is True
        assert self.gate.should_abstain("good morning everyone here") is True

    def test_confirmation_abstains(self):
        assert self.gate.should_abstain("yes that works great for me") is True
        assert self.gate.should_abstain("no I disagree with that approach") is True

    def test_substantive_message_passes(self):
        assert self.gate.should_abstain("What was the architecture decision for the memory system?") is False
        assert self.gate.should_abstain("Let's discuss the lifecycle state machine design") is False

    def test_question_passes(self):
        assert self.gate.should_abstain("How does the proactive retrieval gateway work?") is False

    def test_post_retrieval_low_score_abstains(self):
        assert self.gate.should_abstain_post_retrieval(0.05) is True
        assert self.gate.should_abstain_post_retrieval(0.14) is True

    def test_post_retrieval_good_score_passes(self):
        assert self.gate.should_abstain_post_retrieval(0.5) is False
        assert self.gate.should_abstain_post_retrieval(0.9) is False

    def test_post_retrieval_at_threshold(self):
        assert self.gate.should_abstain_post_retrieval(0.15) is False

    def test_custom_threshold(self):
        strict_gate = AbstainGate(min_words=5, score_threshold=0.5)
        assert strict_gate.should_abstain("four word message here") is True
        assert strict_gate.should_abstain_post_retrieval(0.4) is True
