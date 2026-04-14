from __future__ import annotations

import pytest

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult
from agent_platform.executors.registry import ExecutorNotFoundError, ExecutorRegistry


class DummyExecutor(BaseNodeExecutor):
    def execute(self, context, node) -> ExecutorResult:
        return ExecutorResult(status="SUCCEEDED", output={"ok": True}, logs=[])


class DummyNode:
    def __init__(self, node_type: str) -> None:
        self.type = node_type


def test_registry_register_and_get() -> None:
    registry = ExecutorRegistry()
    executor = DummyExecutor()

    registry.register("llm_generate", executor)

    assert registry.get("llm_generate") is executor


def test_registry_get_raises_for_unknown_node_type() -> None:
    registry = ExecutorRegistry()

    with pytest.raises(ExecutorNotFoundError):
        registry.get("unknown")


def test_registry_resolve_for_node() -> None:
    registry = ExecutorRegistry()
    executor = DummyExecutor()
    registry.register("llm_review", executor)

    resolved = registry.resolve_for_node(DummyNode("llm_review"))

    assert resolved is executor
