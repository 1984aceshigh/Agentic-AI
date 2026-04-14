from __future__ import annotations

from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


class LLMReviewExecutor(BaseNodeExecutor):
    """Dummy executor for llm_review nodes."""

    def execute(self, context: Any, node: Any) -> ExecutorResult:
        try:
            prepared = self.prepare_input(context=context, node=node)
            node_id = getattr(node, "id", "unknown_node")
            return ExecutorResult(
                status="SUCCEEDED",
                output={"review": f"reviewed by {node_id}", "score": 80},
                logs=[
                    f"Prepared {len(prepared['resolved_inputs'])} resolved input(s) for llm_review."
                ],
            )
        except Exception as exc:  # pragma: no cover - defensive path
            return self.handle_error(exc)
