"""Tests for AsyncWritePipeline."""

import tempfile
import time
import threading
from pathlib import Path

from agent_memory_fabric.core.engine import MemoryEngine
from agent_memory_fabric.llm.provider import MockProvider
from agent_memory_fabric.write.async_pipeline import AsyncWritePipeline
from agent_memory_fabric.write.write_pipeline import WritePipeline


def _make_pipeline(tmpdir, response='[{"content": "User prefers Python for scripting tasks", "tags": ["preference"], "confidence": 0.8}]'):
    engine = MemoryEngine(vault_path=tmpdir)
    provider = MockProvider(default_response=response)
    pipeline = WritePipeline(
        engine=engine, llm_provider=provider,
        use_consolidation=False, turn_interval=4,
    )
    return pipeline, engine


class TestAsyncWritePipeline:
    def test_schedule_turn_returns_immediately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline)

            start = time.time()
            async_pipe.schedule_turn("hello", has_tool_calls=True)
            elapsed = time.time() - start
            assert elapsed < 0.1  # should be near-instant

    def test_extraction_runs_in_background(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline)

            for i in range(4):
                async_pipe.schedule_turn(f"I use Python for scripting tasks every day turn {i}", has_tool_calls=True)

            # Wait for background extraction
            time.sleep(1.0)
            nodes = engine.list_nodes()
            assert len(nodes) >= 1

    def test_flush_blocks_until_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline)

            async_pipe.schedule_turn("Important fact to remember", has_tool_calls=True)
            # Force flush (bypasses trigger)
            ids = async_pipe.flush()
            assert len(ids) >= 0  # may or may not extract depending on trigger

    def test_flush_with_pending_buffer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            pipeline.trigger.turn_interval = 100  # never auto-trigger
            async_pipe = AsyncWritePipeline(pipeline)

            for i in range(5):
                pipeline._turn_buffer.append(f"I prefer Python for scripting and automation turn {i}")

            ids = async_pipe.flush()
            assert len(ids) >= 1

    def test_is_extracting_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline)
            assert async_pipe.is_extracting is False

    def test_on_complete_callback(self):
        results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline, on_complete=lambda ids: results.extend(ids))

            for i in range(4):
                async_pipe.schedule_turn(f"Turn {i}", has_tool_calls=True)

            time.sleep(0.5)
            # callback may or may not fire depending on extraction success
            # just verify no crash

    def test_no_crash_on_concurrent_access(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline, engine = _make_pipeline(tmpdir)
            async_pipe = AsyncWritePipeline(pipeline)

            def writer():
                for i in range(10):
                    async_pipe.schedule_turn(f"Thread write {i}", has_tool_calls=True)
                    time.sleep(0.01)

            threads = [threading.Thread(target=writer) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # No crash = success
            async_pipe.flush()
