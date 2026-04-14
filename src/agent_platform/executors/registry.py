from __future__ import annotations

from typing import Any

from agent_platform.executors.base import BaseNodeExecutor


class ExecutorNotFoundError(KeyError):
    """Raised when an executor is requested for an unknown node type."""

    def __init__(self, node_type: str) -> None:
        super().__init__(f"Executor not found for node_type={node_type}")
        self.node_type = node_type


class ExecutorRegistry:
    """Registry for node-type specific executors."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseNodeExecutor] = {}

    def register(self, node_type: str, executor: BaseNodeExecutor) -> None:
        self._executors[node_type] = executor

    def get(self, node_type: str) -> BaseNodeExecutor:
        executor = self._executors.get(node_type)
        if executor is None:
            raise ExecutorNotFoundError(node_type)
        return executor

    def resolve_for_node(self, node: Any) -> BaseNodeExecutor:
        node_type = getattr(node, "type", None)
        if not node_type:
            raise ExecutorNotFoundError("<missing>")
        return self.get(node_type)
