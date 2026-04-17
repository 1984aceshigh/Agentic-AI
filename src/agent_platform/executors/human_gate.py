from __future__ import annotations

from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


class HumanGateExecutor(BaseNodeExecutor):
    """Placeholder executor for human_gate nodes."""

    node_type = "human_gate"

    def execute(self, context: Any, node: Any) -> ExecutorResult:
        try:
            prepared = self.prepare_input(context=context, node=node)
            return ExecutorResult(
                status="WAITING_HUMAN",
                output={"pending_input": prepared["resolved_inputs"]},
                logs=["human_gate reached; waiting for human action."],
                requires_human_action=True,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            return self.handle_error(exc)
