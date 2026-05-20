"""Tests for Policy-Based Composition."""

from agent_memory_fabric.core.node import MemoryType
from agent_memory_fabric.core.policy import MemoryPolicy, PolicyRegistry


class MockExtractor:
    def extract(self, text, context=None):
        return [{"content": text}]


class MockConsolidator:
    def consolidate(self, new_content, existing_contents):
        return {"decision": "add", "content": new_content}


class TestMemoryPolicy:
    def test_create_policy(self):
        policy = MemoryPolicy(name="test", memory_type=MemoryType.USER)
        assert policy.name == "test"
        assert policy.memory_type == MemoryType.USER
        assert policy.enabled is True

    def test_set_extractor(self):
        policy = MemoryPolicy(name="test", memory_type=MemoryType.USER)
        ext = MockExtractor()
        policy.set_extractor(ext)
        assert policy.extractor is ext

    def test_set_consolidator(self):
        policy = MemoryPolicy(name="test", memory_type=MemoryType.USER)
        cons = MockConsolidator()
        policy.set_consolidator(cons)
        assert policy.consolidator is cons

    def test_consolidator_optional(self):
        policy = MemoryPolicy(name="test", memory_type=MemoryType.USER)
        assert policy.consolidator is None


class TestPolicyRegistry:
    def test_register_and_get(self):
        registry = PolicyRegistry()
        policy = MemoryPolicy(name="user_facts", memory_type=MemoryType.USER)
        registry.register(policy)
        assert registry.get(MemoryType.USER) is policy

    def test_get_missing_returns_none(self):
        registry = PolicyRegistry()
        assert registry.get(MemoryType.USER) is None

    def test_list_policies(self):
        registry = PolicyRegistry()
        registry.register(MemoryPolicy(name="p1", memory_type=MemoryType.USER))
        registry.register(MemoryPolicy(name="p2", memory_type=MemoryType.PROJECT))
        assert registry.count == 2
        assert len(registry.list_policies()) == 2

    def test_list_enabled_filters_disabled(self):
        registry = PolicyRegistry()
        registry.register(MemoryPolicy(name="active", memory_type=MemoryType.USER, enabled=True))
        registry.register(MemoryPolicy(name="disabled", memory_type=MemoryType.PROJECT, enabled=False))
        enabled = registry.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == "active"

    def test_register_overwrites_same_type(self):
        registry = PolicyRegistry()
        registry.register(MemoryPolicy(name="old", memory_type=MemoryType.USER))
        registry.register(MemoryPolicy(name="new", memory_type=MemoryType.USER))
        assert registry.get(MemoryType.USER).name == "new"
        assert registry.count == 1
