from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent_platform.models.execution import ExecutionContext, ExecutionEvent


class ExecutionContextNotFoundError(KeyError):
    """Raised when the requested execution context does not exist."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(f"ExecutionContext not found: execution_id={execution_id}")
        self.execution_id = execution_id


class ExecutionContextManager:
    """In-memory manager for workflow execution contexts."""

    def __init__(self) -> None:
        self._contexts: dict[str, ExecutionContext] = {}

    def create_context(
        self,
        workflow_id: str,
        workflow_version: str | None = None,
        global_inputs: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        execution_id = str(uuid4())

        context = ExecutionContext(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            global_inputs=dict(global_inputs or {}),
            node_outputs={},
            node_states={},
            artifacts={},
            events=[],
            metadata={"logs": []},
        )
        self.save_context(context)
        return context

    def get_context(self, execution_id: str) -> ExecutionContext:
        context = self._contexts.get(execution_id)
        if context is None:
            raise ExecutionContextNotFoundError(execution_id)
        return context

    def save_context(self, context: ExecutionContext) -> None:
        self._contexts[context.execution_id] = context

    def update_node_state(
        self,
        execution_id: str,
        node_id: str,
        status: str,
    ) -> ExecutionContext:
        context = self.get_context(execution_id)
        context.node_states[node_id] = status
        return context

    def append_log(self, execution_id: str, message: str) -> ExecutionContext:
        context = self.get_context(execution_id)
        logs = context.metadata.setdefault("logs", [])

        if not isinstance(logs, list):
            raise TypeError("ExecutionContext.metadata['logs'] must be a list.")

        logs.append(message)
        return context

    def set_node_output(
        self,
        execution_id: str,
        node_id: str,
        output: dict[str, Any],
    ) -> ExecutionContext:
        context = self.get_context(execution_id)
        node_output = context.node_outputs.setdefault(node_id, {})
        node_output.update(output)
        return context

    def append_event(
        self,
        execution_id: str,
        event: ExecutionEvent,
    ) -> ExecutionContext:
        context = self.get_context(execution_id)
        context.events.append(event)
        return context

    def set_artifact(
        self,
        execution_id: str,
        key: str,
        value: Any,
    ) -> ExecutionContext:
        context = self.get_context(execution_id)
        context.artifacts[key] = value
        return context
