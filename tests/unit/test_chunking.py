"""Tests for WindowedChunker."""

from agent_memory_fabric.write.chunking import WindowedChunker


class TestWindowedChunker:
    def test_single_chunk_for_short_conversation(self):
        chunker = WindowedChunker(turn_size=12, past_turn_size=4)
        turns = ["turn 1", "turn 2", "turn 3"]
        chunks = chunker.chunk_conversation(turns)
        assert len(chunks) == 1
        assert chunks[0].current_turns == turns
        assert chunks[0].past_turns == []

    def test_splits_long_conversation(self):
        chunker = WindowedChunker(turn_size=4, past_turn_size=2)
        turns = [f"turn {i}" for i in range(10)]
        chunks = chunker.chunk_conversation(turns)
        assert len(chunks) == 3  # 0-3, 4-7, 8-9

    def test_past_context_included(self):
        chunker = WindowedChunker(turn_size=4, past_turn_size=2)
        turns = [f"turn {i}" for i in range(10)]
        chunks = chunker.chunk_conversation(turns)
        assert chunks[0].past_turns == []
        assert chunks[1].past_turns == ["turn 2", "turn 3"]
        assert chunks[2].past_turns == ["turn 6", "turn 7"]

    def test_start_end_indices(self):
        chunker = WindowedChunker(turn_size=4, past_turn_size=2)
        turns = [f"turn {i}" for i in range(10)]
        chunks = chunker.chunk_conversation(turns)
        assert chunks[0].start_index == 0
        assert chunks[0].end_index == 3
        assert chunks[1].start_index == 4
        assert chunks[1].end_index == 7
        assert chunks[2].start_index == 8
        assert chunks[2].end_index == 9

    def test_empty_turns(self):
        chunker = WindowedChunker()
        assert chunker.chunk_conversation([]) == []

    def test_exact_turn_size(self):
        chunker = WindowedChunker(turn_size=5, past_turn_size=2)
        turns = [f"turn {i}" for i in range(5)]
        chunks = chunker.chunk_conversation(turns)
        assert len(chunks) == 1
        assert chunks[0].current_turns == turns


class TestFilterCitations:
    def test_keeps_grounded_extractions(self):
        chunker = WindowedChunker()
        current = ["I live in Shanghai and work at Amazon"]
        extracted = ["User lives in Shanghai", "User works at Amazon"]
        filtered = chunker.filter_citations(extracted, current)
        assert len(filtered) == 2

    def test_removes_ungrounded_extractions(self):
        chunker = WindowedChunker()
        current = ["I like coffee"]
        extracted = ["User works at Google in Mountain View"]
        filtered = chunker.filter_citations(extracted, current)
        assert filtered == []

    def test_empty_current_returns_empty(self):
        chunker = WindowedChunker()
        assert chunker.filter_citations(["some fact"], []) == []

    def test_short_words_always_pass(self):
        chunker = WindowedChunker()
        current = ["hi there"]
        extracted = ["hi"]  # all words <= 3 chars
        filtered = chunker.filter_citations(extracted, current)
        assert len(filtered) == 1
