from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


class APIExecutor(BaseNodeExecutor):
    node_type = "api"

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> ExecutorResult:
        config = prepared_input.get("node_config", {})
        operation = str(config.get("operation") or "call_api")
        endpoint = str(config.get("endpoint") or config.get("path") or "")
        payload = config.get("payload")
        if not isinstance(payload, Mapping):
            payload = prepared_input.get("resolved_inputs") or {}
        return ExecutorResult(
            status="SUCCEEDED",
            output={
                "operation": operation,
                "endpoint": endpoint,
                "request": dict(payload),
                "result": f"api operation '{operation}' executed",
            },
            logs=[f"api executor invoked operation={operation}"],
        )
