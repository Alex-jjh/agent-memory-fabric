"""Tests for QueryExpander."""

from agent_memory_fabric.read.query_expansion import QueryExpander


class TestQueryExpander:
    def test_long_query_unchanged(self):
        exp = QueryExpander()
        assert exp.expand("Where does the user currently live and work") == "Where does the user currently live and work"

    def test_short_query_expanded_with_prior(self):
        exp = QueryExpander()
        exp.record_turn("user", "I was discussing my project architecture with the team yesterday")
        result = exp.expand("and then?")
        assert "and then?" in result
        assert "project" in result or "architecture" in result

    def test_short_query_no_prior_unchanged(self):
        exp = QueryExpander()
        assert exp.expand("yes") == "yes"

    def test_exactly_threshold_words_expanded(self):
        exp = QueryExpander(threshold=3)
        exp.record_turn("user", "We talked about memory systems")
        result = exp.expand("what about that")
        assert len(result) > len("what about that")

    def test_above_threshold_not_expanded(self):
        exp = QueryExpander(threshold=3)
        exp.record_turn("user", "Long prior context here")
        query = "tell me more about it please"
        assert exp.expand(query) == query

    def test_uses_both_user_and_assistant_context(self):
        exp = QueryExpander()
        exp.record_turn("user", "I need help with Python scripting")
        exp.record_turn("assistant", "Sure, I can help with Python automation tasks")
        result = exp.expand("ok")
        assert "Python" in result

    def test_context_extraction_truncates_long_messages(self):
        exp = QueryExpander(context_words=3)
        exp.record_turn("user", "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10")
        result = exp.expand("hi")
        assert "word1" in result
        assert "word10" in result
        assert "..." in result
