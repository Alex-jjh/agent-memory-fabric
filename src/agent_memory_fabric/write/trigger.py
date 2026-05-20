"""Write trigger: determines when to run memory extraction."""

from __future__ import annotations

import time

OPTIMIZE_EVERY_N_TURNS = 8
IDLE_TIMEOUT_SECONDS = 120.0


class WriteTrigger:
    """Determines when extraction should run based on turn count, hints, and idle time.

    Skip heuristic: if no tool calls AND no save hint in the turn range,
    the conversation is pure chitchat and unlikely to produce extractable memories.
    """

    def __init__(
        self,
        turn_interval: int = OPTIMIZE_EVERY_N_TURNS,
        idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS,
    ):
        self.turn_interval = turn_interval
        self.idle_timeout_seconds = idle_timeout_seconds
        self._turns_since_extraction: int = 0
        self._last_extraction_time: float = time.time()
        self._has_tool_calls: bool = False
        self._has_save_hint: bool = False

    def record_turn(self, has_tool_calls: bool = False, has_save_hint: bool = False) -> None:
        """Record a new turn with its signals."""
        self._turns_since_extraction += 1
        if has_tool_calls:
            self._has_tool_calls = True
        if has_save_hint:
            self._has_save_hint = True

    def should_extract(self) -> bool:
        """Determine if extraction should run now."""
        elapsed = time.time() - self._last_extraction_time

        if self._has_save_hint:
            return True

        interval_reached = self._turns_since_extraction >= self.turn_interval
        idle_reached = elapsed >= self.idle_timeout_seconds

        if not (interval_reached or idle_reached):
            return False

        if not self._has_tool_calls and not self._has_save_hint:
            return False

        return True

    def mark_extracted(self) -> None:
        """Reset counters after extraction completes."""
        self._turns_since_extraction = 0
        self._last_extraction_time = time.time()
        self._has_tool_calls = False
        self._has_save_hint = False

    @property
    def turns_pending(self) -> int:
        return self._turns_since_extraction
