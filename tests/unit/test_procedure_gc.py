"""Tests for procedure garbage collection."""

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.lifecycle.procedure_gc import is_procedure, should_auto_delete


def _node(tags=None, outcomes=None):
    return MemoryNode(
        id="proc-1", name="test-proc", content="def my_function(): pass",
        tags=tags or [], recent_outcomes=outcomes or [],
    )


class TestIsProcedure:
    def test_procedure_tag(self):
        assert is_procedure(_node(tags=["procedure"])) is True

    def test_tool_strategy_tag(self):
        assert is_procedure(_node(tags=["tool-strategy"])) is True

    def test_non_procedure(self):
        assert is_procedure(_node(tags=["preference"])) is False

    def test_case_insensitive(self):
        assert is_procedure(_node(tags=["Procedure"])) is True


class TestShouldAutoDelete:
    def test_3_failures_0_successes_deletes(self):
        outcomes = [{"success": False}] * 3
        assert should_auto_delete(_node(tags=["procedure"], outcomes=outcomes)) is True

    def test_2_failures_not_enough(self):
        outcomes = [{"success": False}] * 2
        assert should_auto_delete(_node(tags=["procedure"], outcomes=outcomes)) is False

    def test_3_failures_with_success_no_delete(self):
        outcomes = [{"success": False}, {"success": True}, {"success": False}, {"success": False}]
        assert should_auto_delete(_node(tags=["procedure"], outcomes=outcomes)) is False

    def test_non_procedure_never_deleted(self):
        outcomes = [{"success": False}] * 10
        assert should_auto_delete(_node(tags=["preference"], outcomes=outcomes)) is False

    def test_no_outcomes_not_deleted(self):
        assert should_auto_delete(_node(tags=["procedure"], outcomes=[])) is False

    def test_engine_deletes_on_threshold(self):
        import tempfile
        from agent_memory_fabric.core.engine import MemoryEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MemoryEngine(vault_path=tmpdir)
            node = engine.write(content="def broken_function(): raise Error", tags=["procedure"])
            assert node is not None

            # Record 3 failures
            for _ in range(3):
                result = engine.update_confidence(node.id, success=False)

            # Node should be deleted (returns None)
            assert result is None
            assert engine.read(node.id) is None
