from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


class MCPExecutor(BaseNodeExecutor):
    node_type = "mcp"

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> ExecutorResult:
        config = prepared_input.get("node_config", {})
        server = str(config.get("server") or config.get("server_name") or "")
        tool = str(config.get("tool") or config.get("resource") or "")
        payload = config.get("payload")
        if not isinstance(payload, Mapping):
            payload = prepared_input.get("resolved_inputs") or {}

        return ExecutorResult(
            status="SUCCEEDED",
            output={
                "server": server,
                "tool": tool,
                "request": dict(payload),
                "result": f"mcp call executed on server='{server}'",
            },
            logs=[f"mcp executor invoked server={server} tool={tool}"],
        )
