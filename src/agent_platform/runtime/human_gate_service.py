from __future__ import annotations

from typing import Any, Mapping


WAITING_HUMAN = "WAITING_HUMAN"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"


class HumanGateError(RuntimeError):
    """Base error for human gate operations."""


class HumanGateResolutionError(HumanGateError):
    """Raised when a reject target cannot be resolved."""


class HumanGateService:
    """Minimal runtime service for human gate state transitions.

    This service intentionally keeps responsibilities thin:
    it updates node records, optionally mirrors node state to the
    execution context manager, and appends intervention events.

    The service can optionally keep a tiny in-memory view of node
    configuration so that `config.on_reject` can be resolved without
    coupling runtime logic to GraphModel or YAML loading.
    """

    def __init__(self, records_manager: Any, context_manager: Any | None = None) -> None:
        self._records_manager = records_manager
        self._context_manager = context_manager
        self._node_configs_by_execution: dict[str, dict[str, dict[str, Any]]] = {}

    def register_workflow_definition(
        self,
        execution_id: str,
        nodes: list[Mapping[str, Any]] | None = None,
    ) -> None:
        """Register minimal node definitions for fallback resolution.

        Parameters
        ----------
        execution_id:
            Target execution id.
        nodes:
            List of node-like mappings. Each mapping should contain at least
            `id`, and may contain `config` with `on_reject`.
        """
        configs: dict[str, dict[str, Any]] = {}
        for node in nodes or []:
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                continue
            raw_config = node.get("config") or {}
            config = dict(raw_config) if isinstance(raw_config, Mapping) else {}
            configs[node_id] = config
        self._node_configs_by_execution[execution_id] = configs

    def mark_waiting(self, execution_id: str, node_id: str, comment: str | None = None) -> None:
        self._records_manager.mark_node_waiting_human(execution_id, node_id)
        self._set_context_node_state(execution_id, node_id, WAITING_HUMAN)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_waiting",
            node_id=node_id,
            message=comment or "Node is waiting for human approval.",
        )

    def approve(self, execution_id: str, node_id: str, comment: str | None = None) -> str:
        self._records_manager.complete_node_record(
            execution_id,
            node_id,
            output_preview=comment,
        )
        self._set_context_node_state(execution_id, node_id, SUCCEEDED)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_approved",
            node_id=node_id,
            message=comment or "Node was approved by human.",
        )
        return SUCCEEDED

    def reject(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> str:
        target_node_id = self._resolve_reject_target(
            execution_id=execution_id,
            node_id=node_id,
            fallback_node_id=fallback_node_id,
        )

        self._records_manager.fail_node_record(
            execution_id,
            node_id,
            error_message=comment or f"Rejected by human gate. fallback={target_node_id}",
        )
        self._set_context_node_state(execution_id, node_id, FAILED)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_rejected",
            node_id=node_id,
            message=comment or f"Node was rejected by human. fallback={target_node_id}",
            payload_ref=target_node_id,
        )
        return target_node_id

    def _resolve_reject_target(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
    ) -> str:
        if fallback_node_id:
            return fallback_node_id

        configured = self._get_on_reject_from_config(execution_id, node_id)
        if configured:
            return configured

        previous_node_id = self._get_previous_executed_node_id(execution_id, node_id)
        if previous_node_id:
            return previous_node_id

        raise HumanGateResolutionError(
            f"Reject target could not be resolved: execution_id={execution_id}, node_id={node_id}"
        )

    def _get_on_reject_from_config(self, execution_id: str, node_id: str) -> str | None:
        node_configs = self._node_configs_by_execution.get(execution_id, {})
        config = node_configs.get(node_id, {})
        value = config.get("on_reject")
        if value is None:
            return None
        resolved = str(value).strip()
        return resolved or None

    def _get_previous_executed_node_id(self, execution_id: str, node_id: str) -> str | None:
        workflow_record = self._records_manager.get_workflow_record(execution_id)
        node_records = list(getattr(workflow_record, "node_records", []) or [])

        current_index: int | None = None
        for index, record in enumerate(node_records):
            if getattr(record, "node_id", None) == node_id:
                current_index = index
                break

        if current_index is None or current_index == 0:
            return None

        previous_record = node_records[current_index - 1]
        previous_node_id = getattr(previous_record, "node_id", None)
        if previous_node_id is None:
            return None
        return str(previous_node_id)

    def _set_context_node_state(self, execution_id: str, node_id: str, status: str) -> None:
        if self._context_manager is None:
            return
        update_node_state = getattr(self._context_manager, "update_node_state", None)
        if callable(update_node_state):
            update_node_state(execution_id, node_id, status)

    def _append_event(
        self,
        execution_id: str,
        event_type: str,
        node_id: str | None = None,
        message: str | None = None,
        payload_ref: str | None = None,
    ) -> None:
        self._records_manager.append_event(
            execution_id=execution_id,
            event_type=event_type,
            node_id=node_id,
            message=message,
            payload_ref=payload_ref,
        )
