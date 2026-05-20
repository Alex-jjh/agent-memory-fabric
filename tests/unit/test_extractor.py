"""Tests for memory extractor."""

from agent_memory_fabric.write.extractor import (
    ExtractionResult,
    MemoryExtractor,
    generate_name,
    suggest_tags,
)


class TestGenerateName:
    def test_basic(self):
        name = generate_name("User prefers dark mode")
        assert name.startswith("user-prefers-dark-mode-")
        assert len(name) <= 50

    def test_strips_punctuation(self):
        name = generate_name("Hello, world! How are you?")
        assert name.startswith("hello-world-how-are-you-")

    def test_truncates_at_50(self):
        long = " ".join(["superlongword"] * 10)
        name = generate_name(long)
        assert len(name) <= 50

    def test_empty_content(self):
        name = generate_name("")
        assert name.startswith("unnamed-")

    def test_only_punctuation(self):
        name = generate_name("... ??? !!!")
        assert name.startswith("unnamed-")


class TestSuggestTags:
    def test_preference(self):
        tags = suggest_tags("User prefers dark mode always")
        assert "preference" in tags

    def test_decision(self):
        tags = suggest_tags("We decided to use Python")
        assert "decision" in tags

    def test_insight(self):
        tags = suggest_tags("I discovered a new pattern")
        assert "insight" in tags

    def test_temporal(self):
        tags = suggest_tags("Meeting scheduled for next week")
        assert "temporal" in tags

    def test_no_tags(self):
        tags = suggest_tags("The sky is blue")
        assert tags == []


class TestMemoryExtractor:
    def setup_method(self):
        self.extractor = MemoryExtractor()

    def test_extracts_meaningful_sentences(self):
        text = "User always prefers dark mode for all applications. The weather is nice today."
        results = self.extractor.extract(text)
        assert len(results) >= 1
        assert any("dark mode" in r.content for r in results)

    def test_filters_short_sentences(self):
        text = "Ok. Sure. Got it. Thanks."
        results = self.extractor.extract(text)
        assert results == []

    def test_filters_noise_patterns(self):
        text = "Ok I understand that completely and will do it."
        results = self.extractor.extract(text)
        assert results == []

    def test_handles_multiline(self):
        text = """- User prefers Python for backend development
- User likes TypeScript for frontend
- Short
"""
        results = self.extractor.extract(text)
        assert len(results) == 2

    def test_confidence_boost_for_explicit(self):
        text = "Always remember to use dark mode in all editors."
        results = self.extractor.extract(text)
        assert len(results) == 1
        assert results[0].confidence > 0.5

    def test_confidence_reduction_for_hedging(self):
        text = "I think maybe we should probably consider using a different approach."
        results = self.extractor.extract(text)
        if results:
            assert results[0].confidence <= 0.5

    def test_returns_extraction_results(self):
        text = "We decided to use the lifecycle state machine for memory management."
        results = self.extractor.extract(text)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, ExtractionResult)
        assert r.suggested_name != ""
        assert "decision" in r.suggested_tags

    def test_min_confidence_filtering(self):
        extractor = MemoryExtractor(min_confidence=0.9)
        text = "Some regular sentence about normal things in life."
        results = extractor.extract(text)
        assert results == []

    def test_extract_from_conversation(self):
        text = """User: I always use vim keybindings in every editor.
Assistant: Got it, I'll remember your preference for vim keybindings."""
        results = self.extractor.extract(text)
        assert len(results) >= 1


class TestLLMExtractor:
    def test_parses_valid_json_response(self):
        from agent_memory_fabric.llm.provider import MockProvider
        from agent_memory_fabric.write.extractor import LLMExtractor

        provider = MockProvider(default_response='[{"content": "User lives in Shanghai", "tags": ["profile"], "confidence": 0.9}]')
        extractor = LLMExtractor(provider=provider, max_gleaning_passes=0)
        results = extractor.extract("I live in Shanghai")
        assert len(results) == 1
        assert "Shanghai" in results[0].content
        assert results[0].confidence == 0.9

    def test_handles_invalid_json(self):
        from agent_memory_fabric.llm.provider import MockProvider
        from agent_memory_fabric.write.extractor import LLMExtractor

        provider = MockProvider(default_response="not json at all")
        extractor = LLMExtractor(provider=provider)
        results = extractor.extract("test input")
        assert results == []

    def test_handles_provider_exception(self):
        from agent_memory_fabric.llm.provider import MockProvider
        from agent_memory_fabric.write.extractor import LLMExtractor

        class FailProvider:
            def complete(self, system, user):
                raise RuntimeError("API error")

        extractor = LLMExtractor(provider=FailProvider(), max_gleaning_passes=0)
        results = extractor.extract("test")
        assert results == []

    def test_gleaning_adds_results(self):
        from agent_memory_fabric.llm.provider import MockProvider
        from agent_memory_fabric.write.extractor import LLMExtractor

        provider = MockProvider()
        provider.set_responses([
            '[{"content": "User prefers dark mode", "tags": ["preference"], "confidence": 0.8}]',
            '[{"content": "User works at Amazon", "tags": ["profile"], "confidence": 0.7}]',
        ])
        extractor = LLMExtractor(provider=provider, max_gleaning_passes=1)
        results = extractor.extract("I prefer dark mode and I work at Amazon")
        assert len(results) == 2

    def test_filters_short_content(self):
        from agent_memory_fabric.llm.provider import MockProvider
        from agent_memory_fabric.write.extractor import LLMExtractor

        provider = MockProvider(default_response='[{"content": "ok", "tags": [], "confidence": 0.5}]')
        extractor = LLMExtractor(provider=provider, max_gleaning_passes=0)
        results = extractor.extract("test")
        assert results == []
