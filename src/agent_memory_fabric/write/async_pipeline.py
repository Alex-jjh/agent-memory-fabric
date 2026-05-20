"""Async write pipeline: non-blocking extraction via background thread."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from agent_memory_fabric.write.write_pipeline import WritePipeline


class AsyncWritePipeline:
    """Wraps WritePipeline to run extraction on a background thread.

    The main conversation path calls schedule_turn() which returns immediately.
    Extraction runs asynchronously; results are persisted and available for
    the NEXT turn's retrieval.

    Coalescing: if new turns arrive during extraction, they accumulate in the
    buffer. When extraction finishes, a trailing run processes the new turns.
    """

    def __init__(
        self,
        pipeline: "WritePipeline",
        on_complete: Callable[[list[str]], None] | None = None,
    ):
        self._pipeline = pipeline
        self._on_complete = on_complete
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pending_after: list[str] = []
        self._in_progress = False

    def schedule_turn(
        self,
        message: str,
        has_tool_calls: bool = False,
        has_save_hint: bool = False,
    ) -> None:
        """Buffer turn and start background extraction if trigger fires."""
        with self._lock:
            self._pipeline._turn_buffer.append(message)
            self._pipeline.trigger.record_turn(
                has_tool_calls=has_tool_calls,
                has_save_hint=has_save_hint,
            )

            if self._in_progress:
                self._pending_after.append(message)
                return

            should = self._pipeline.trigger.should_extract()
            buffer_overflow = len(self._pipeline._turn_buffer) >= self._pipeline._max_buffer_turns

            if not should and not buffer_overflow:
                return

            self._in_progress = True
            self._pending_after = []

        self._thread = threading.Thread(target=self._run_background, daemon=True)
        self._thread.start()

    def _run_background(self) -> None:
        """Background thread target: run extraction then check for trailing work.

        While in_progress=True, schedule_turn appends to _pending_after (not _turn_buffer),
        so _turn_buffer is safe to read here without the lock during extraction.
        """
        try:
            created_ids = self._pipeline._run_extraction()
            self._pipeline.trigger.mark_extracted()

            with self._lock:
                self._pipeline._turn_buffer.clear()

            if self._on_complete and created_ids:
                self._on_complete(created_ids)
        finally:
            self._check_trailing()

    def _check_trailing(self) -> None:
        """After extraction, check if new turns arrived that need processing."""
        with self._lock:
            if self._pending_after:
                self._pipeline._turn_buffer = list(self._pending_after)
                self._pending_after = []

                if self._pipeline.trigger.should_extract():
                    self._thread = threading.Thread(target=self._run_background, daemon=True)
                    self._thread.start()
                    return

            self._in_progress = False

    def flush(self, timeout: float = 30.0) -> list[str]:
        """Synchronously extract remaining buffer. Blocks until complete."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        with self._lock:
            if not self._pipeline._turn_buffer:
                return []
            self._in_progress = True

        created_ids = self._pipeline._run_extraction()
        self._pipeline.trigger.mark_extracted()
        self._pipeline._turn_buffer.clear()

        with self._lock:
            self._in_progress = False
            self._pending_after = []

        return created_ids

    @property
    def is_extracting(self) -> bool:
        return self._in_progress

    @property
    def pending_turns(self) -> int:
        with self._lock:
            return len(self._pipeline._turn_buffer) + len(self._pending_after)
