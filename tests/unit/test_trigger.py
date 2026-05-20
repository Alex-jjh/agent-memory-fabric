"""Tests for WriteTrigger."""

import time

from agent_memory_fabric.write.trigger import WriteTrigger


class TestWriteTrigger:
    def test_does_not_extract_before_interval(self):
        trigger = WriteTrigger(turn_interval=8)
        for _ in range(5):
            trigger.record_turn(has_tool_calls=True)
        assert trigger.should_extract() is False

    def test_extracts_at_interval_with_tool_calls(self):
        trigger = WriteTrigger(turn_interval=8)
        for _ in range(8):
            trigger.record_turn(has_tool_calls=True)
        assert trigger.should_extract() is True

    def test_skips_pure_chitchat(self):
        trigger = WriteTrigger(turn_interval=4)
        for _ in range(4):
            trigger.record_turn(has_tool_calls=False, has_save_hint=False)
        assert trigger.should_extract() is False

    def test_save_hint_triggers_immediately(self):
        trigger = WriteTrigger(turn_interval=100)
        trigger.record_turn(has_save_hint=True)
        assert trigger.should_extract() is True

    def test_idle_timeout_with_tool_calls(self):
        trigger = WriteTrigger(turn_interval=100, idle_timeout_seconds=0.01)
        trigger.record_turn(has_tool_calls=True)
        time.sleep(0.02)
        assert trigger.should_extract() is True

    def test_idle_timeout_without_tool_calls_skips(self):
        trigger = WriteTrigger(turn_interval=100, idle_timeout_seconds=0.01)
        trigger.record_turn(has_tool_calls=False)
        time.sleep(0.02)
        assert trigger.should_extract() is False

    def test_mark_extracted_resets(self):
        trigger = WriteTrigger(turn_interval=4)
        for _ in range(4):
            trigger.record_turn(has_tool_calls=True)
        assert trigger.should_extract() is True
        trigger.mark_extracted()
        assert trigger.should_extract() is False
        assert trigger.turns_pending == 0

    def test_turns_pending_tracks_count(self):
        trigger = WriteTrigger()
        assert trigger.turns_pending == 0
        trigger.record_turn()
        trigger.record_turn()
        assert trigger.turns_pending == 2
