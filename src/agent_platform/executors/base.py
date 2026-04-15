from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"


@dataclass(slots=True)
class ExecutorResult:
    """Unified result returned by node executors."""

    status: str
    output: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    input_preview: str | None = None
    logs: list[str] = field(default_factory=list)
    error_message: str | None = None
    requires_human_action: bool = False


class BaseNodeExecutor(ABC):
    """Common execution contract for node executors."""

    node_type: str = ""

    def run(self, *, spec: Any, node: Any, context: Any | None = None) -> ExecutorResult:
        try:
            prepared_input = self.prepare_input(spec=spec, node=node, context=context)
            try:
                execution_result = self.execute(
                    spec=spec,
                    node=node,
                    context=context,
                    prepared_input=prepared_input,
                )
            except TypeError:
                # Backward compatibility for executors that still expose
                # execute(context, node) -> ExecutorResult.
                execution_result = self.execute(context, node)

            if isinstance(execution_result, ExecutorResult):
                return execution_result

            output = execution_result
            summary = self.summarize_output(output)
            return ExecutorResult(
                status=SUCCEEDED,
                output=output,
                summary=summary,
            )
        except Exception as exc:  # pragma: no cover - exercised via concrete tests
            return self.handle_error(exc, spec=spec, node=node, context=context)

    def prepare_input(
        self,
        *,
        spec: Any | None = None,
        node: Any,
        context: Any | None = None,
    ) -> Any:
        """Prepare executor-specific input from workflow/node/context.

        Default implementation keeps backward compatibility with executors that
        call `self.prepare_input(context=context, node=node)` directly.
        """
        node_config = self._get_attr_or_key(node, "config") or {}
        node_input = self._get_attr_or_key(node, "input") or {}
        global_inputs = self._get_attr_or_key(context, "global_inputs") or {}
        node_outputs = self._get_attr_or_key(context, "node_outputs") or {}

        resolved_inputs: dict[str, Any] = {}
        from_refs = self._get_attr_or_key(node_input, "from") or []
        if isinstance(from_refs, list):
            for ref in from_refs:
                if not isinstance(ref, dict):
                    continue
                upstream_node = ref.get("node")
                upstream_key = ref.get("key")
                alias = ref.get("as") or upstream_key
                if not upstream_node or not upstream_key or not alias:
                    continue
                upstream_output = self._get_attr_or_key(node_outputs, upstream_node) or {}
                if isinstance(upstream_output, dict) and upstream_key in upstream_output:
                    resolved_inputs[str(alias)] = upstream_output[upstream_key]

        return {
            "node_config": dict(node_config) if isinstance(node_config, dict) else {},
            "node_input": dict(node_input) if isinstance(node_input, dict) else {},
            "global_inputs": dict(global_inputs) if isinstance(global_inputs, dict) else {},
            "node_outputs": dict(node_outputs) if isinstance(node_outputs, dict) else {},
            "resolved_inputs": resolved_inputs,
        }

    @abstractmethod
    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: Any,
    ) -> dict[str, Any]:
        """Execute the node-specific logic."""

    def summarize_output(self, output: dict[str, Any]) -> str | None:
        if isinstance(output, ExecutorResult):
            if output.summary:
                return output.summary
            output = output.output
        if not output:
            return None
        return ", ".join(sorted(output.keys()))

    def handle_error(
        self,
        error: Exception,
        *,
        spec: Any | None = None,
        node: Any | None = None,
        context: Any | None = None,
    ) -> ExecutorResult:
        return ExecutorResult(
            status=FAILED,
            output={},
            error_message=str(error),
        )

    def _get_attr_or_key(self, obj: Any, field_name: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(field_name)
        return getattr(obj, field_name, None)


class ExecutorRegistry:
    """Simple in-memory registry for node executors."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseNodeExecutor] = {}

    def register(self, node_type: str, executor: BaseNodeExecutor) -> None:
        self._executors[node_type] = executor

    def register_executor(self, executor: BaseNodeExecutor) -> None:
        if not executor.node_type:
            raise ValueError("executor.node_type が空です。")
        self._executors[executor.node_type] = executor

    def get(self, node_type: str) -> BaseNodeExecutor:
        if node_type not in self._executors:
            raise KeyError(f"node_type '{node_type}' の executor が登録されていません。")
        return self._executors[node_type]

    def has(self, node_type: str) -> bool:
        return node_type in self._executors

    def resolve_for_node(self, node: Any) -> BaseNodeExecutor:
        node_type = getattr(node, "type", None)
        if node_type is None and isinstance(node, dict):
            node_type = node.get("type")
        if not node_type:
            raise KeyError("node.type が取得できません。")
        return self.get(node_type)
