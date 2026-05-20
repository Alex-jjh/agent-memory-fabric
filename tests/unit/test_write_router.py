"""Tests for write router — dedup + classification."""

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, WriteOperation
from agent_memory_fabric.write.router import WriteRouter, compute_hash, dedup_check


class TestComputeHash:
    def test_deterministic(self):
        assert compute_hash("hello") == compute_hash("hello")

    def test_case_insensitive(self):
        assert compute_hash("Hello World") == compute_hash("hello world")

    def test_strips_whitespace(self):
        assert compute_hash("  hello  ") == compute_hash("hello")

    def test_different_content_different_hash(self):
        assert compute_hash("hello") != compute_hash("world")


class TestDedupCheck:
    def test_detects_duplicate(self):
        hashes = {compute_hash("existing content")}
        assert dedup_check("existing content", hashes) is True

    def test_passes_new_content(self):
        hashes = {compute_hash("existing content")}
        assert dedup_check("new content", hashes) is False

    def test_empty_hash_set(self):
        assert dedup_check("anything", set()) is False


class TestClassify:
    def setup_method(self):
        self.router = WriteRouter()

    def test_duplicate_returns_none(self):
        hashes = {compute_hash("already stored")}
        result = self.router.classify("already stored", existing_hashes=hashes)
        assert result is None

    def test_new_content_returns_append(self):
        result = self.router.classify("brand new content")
        assert result == WriteOperation.APPEND

    def test_new_content_with_existing_returns_append(self):
        existing = MemoryNode(name="test", content="old content")
        result = self.router.classify("new content", existing_node=existing)
        assert result == WriteOperation.APPEND

    def test_same_content_with_existing_returns_append(self):
        existing = MemoryNode(name="test", content="same content")
        result = self.router.classify("same content", existing_node=existing)
        assert result == WriteOperation.APPEND


class TestHasTTLPattern:
    def setup_method(self):
        self.router = WriteRouter()

    def test_detects_deadline(self):
        assert self.router.has_ttl_pattern("Deadline is 2026-05-25") is True

    def test_detects_expires(self):
        assert self.router.has_ttl_pattern("This expires at 15:00") is True

    def test_no_pattern(self):
        assert self.router.has_ttl_pattern("User prefers dark mode") is False


class TestExecute:
    def setup_method(self):
        self.router = WriteRouter()

    def test_append_creates_new_node(self):
        node = self.router.execute("New fact about user", WriteOperation.APPEND)
        assert node is not None
        assert node.state == LifecycleState.ACTIVE
        assert node.content == "New fact about user"

    def test_replace_updates_target(self):
        target = MemoryNode(name="target", content="old")
        result = self.router.execute("new content", WriteOperation.REPLACE, target_node=target)
        assert result.content == "new content"
        assert result.name == "target"

    def test_expire_transitions_target(self):
        target = MemoryNode(name="meeting", content="3pm meeting")
        result = self.router.execute("", WriteOperation.EXPIRE, target_node=target)
        assert result.state == LifecycleState.EXPIRED

    def test_synthesize_creates_decided_node(self):
        result = self.router.execute("Summary of discussions", WriteOperation.SYNTHESIZE)
        assert result.state == LifecycleState.DECIDED
        assert "synthesis-" in result.name

    def test_generate_name_from_content(self):
        node = self.router.execute("User prefers dark mode always", WriteOperation.APPEND)
        assert node.name == "user-prefers-dark-mode-always"

    def test_generate_name_truncates(self):
        long_content = " ".join(["word"] * 20)
        node = self.router.execute(long_content, WriteOperation.APPEND)
        assert len(node.name) <= 50
