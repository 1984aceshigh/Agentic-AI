from __future__ import annotations

from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


SUPPORTED_HUMAN_GATE_TASKS = {"entry_input", "human_task", "approval"}


def resolve_human_gate_task(node_config: dict[str, Any]) -> str:
    task = str(node_config.get("task") or "").strip().lower()
    if task in SUPPORTED_HUMAN_GATE_TASKS:
        return task

    # backward compatibility
    gate_type = str(node_config.get("gate_type") or "").strip().lower()
    if gate_type == "review":
        return "human_task"
    return "approval"


class HumanGateExecutor(BaseNodeExecutor):
    """Executor for human_gate nodes.

    Human gate can represent three kinds of human work:
    1) entry_input: workflow initial business input
    2) human_task: a regular human work step in the flow
    3) approval: approval / go-no-go decision for AI outputs
    """

    node_type = "human_gate"

    def execute(self, context: Any, node: Any) -> ExecutorResult:
        try:
            prepared = self.prepare_input(context=context, node=node)
            node_config = prepared.get("node_config") or {}
            task = resolve_human_gate_task(node_config)
            required_fields = node_config.get("required_fields")
            if not isinstance(required_fields, list):
                required_fields = []
            required_fields = [str(item).strip() for item in required_fields if str(item).strip()]

            instructions = str(node_config.get("instructions") or "").strip() or None
            allow_files = bool(node_config.get("allow_files", task == "entry_input"))
            approval_options = node_config.get("approval_options")
            if isinstance(approval_options, list):
                normalized_approval_options = [str(item).strip() for item in approval_options if str(item).strip()]
            else:
                normalized_approval_options = []
            if task == "approval" and not normalized_approval_options:
                normalized_approval_options = ["承認", "否認"]

            input_preview = f"human_gate task={task}"
            if required_fields:
                input_preview += f", required_fields={', '.join(required_fields)}"

            return ExecutorResult(
                status="WAITING_HUMAN",
                output={
                    "human_gate_task": task,
                    "pending_input": prepared["resolved_inputs"],
                    "required_fields": required_fields,
                    "allow_files": allow_files,
                    "instructions": instructions,
                    "approval_options": normalized_approval_options,
                },
                input_preview=input_preview,
                logs=[f"human_gate reached ({task}); waiting for human action."],
                requires_human_action=True,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            return self.handle_error(exc)
