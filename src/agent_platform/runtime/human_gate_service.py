from __future__ import annotations

import json
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
        self._refresh_workflow_status(execution_id)
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
        self._refresh_workflow_status(execution_id)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_approved",
            node_id=node_id,
            message=comment or "Node was approved by human.",
        )
        return SUCCEEDED

    def decide(
        self,
        execution_id: str,
        node_id: str,
        decision_option: str,
        comment: str | None = None,
    ) -> str:
        selected_option = str(decision_option or "").strip()
        if not selected_option:
            raise ValueError("decision_option is required.")

        approval_routes = self._get_approval_routes(execution_id=execution_id, node_id=node_id)
        next_node = approval_routes.get(selected_option)
        if isinstance(next_node, list):
            next_node = next((str(item).strip() for item in next_node if str(item).strip()), None)
        elif isinstance(next_node, str):
            next_node = next_node.strip() or None
        else:
            next_node = None

        self._records_manager.complete_node_record(
            execution_id,
            node_id,
            output_preview=comment or selected_option,
        )
        self._set_context_node_state(execution_id, node_id, SUCCEEDED)
        self._set_context_node_output(
            execution_id,
            node_id,
            {
                "selected_option": selected_option,
                "next_node": next_node,
                "human_comment": comment,
                "human_gate_submission": "approved",
            },
        )
        self._refresh_workflow_status(execution_id)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_approved",
            node_id=node_id,
            message=comment or f"Node approved with option '{selected_option}'.",
            payload_ref=next_node,
        )
        return SUCCEEDED

    def submit(
        self,
        execution_id: str,
        node_id: str,
        human_input: Mapping[str, Any] | None = None,
        comment: str | None = None,
    ) -> str:
        payload = dict(human_input or {})
        self._records_manager.complete_node_record(
            execution_id,
            node_id,
            output_preview=comment or ("submitted" if payload else None),
        )
        self._set_context_node_state(execution_id, node_id, SUCCEEDED)
        self._set_context_node_output(
            execution_id,
            node_id,
            {
                "result": self._build_submission_result(payload),
                "human_input": payload,
                "human_comment": comment,
                "human_gate_submission": "submitted",
            },
        )
        self._refresh_workflow_status(execution_id)
        self._append_event(
            execution_id=execution_id,
            event_type="human_gate_submitted",
            node_id=node_id,
            message=comment or "Node input submitted by human.",
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
        self._refresh_workflow_status(execution_id)
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

    def _set_context_node_output(self, execution_id: str, node_id: str, output: Mapping[str, Any]) -> None:
        if self._context_manager is None:
            return
        set_node_output = getattr(self._context_manager, "set_node_output", None)
        if callable(set_node_output):
            set_node_output(execution_id, node_id, dict(output))

    def _refresh_workflow_status(self, execution_id: str) -> None:
        get_workflow_record = getattr(self._records_manager, "get_workflow_record", None)
        set_workflow_status = getattr(self._records_manager, "set_workflow_status", None)
        if not callable(get_workflow_record) or not callable(set_workflow_status):
            return

        workflow_record = get_workflow_record(execution_id)
        node_records = list(getattr(workflow_record, "node_records", []) or [])
        statuses = {
            str(getattr(record, "status", "")).strip().upper()
            for record in node_records
            if str(getattr(record, "status", "")).strip()
        }

        if "FAILED" in statuses:
            workflow_status = FAILED
        elif WAITING_HUMAN in statuses:
            workflow_status = WAITING_HUMAN
        elif "RUNNING" in statuses:
            workflow_status = "RUNNING"
        else:
            workflow_status = SUCCEEDED

        set_workflow_status(execution_id, workflow_status)

    # UI adapters compatibility methods
    def approve_node(
        self,
        execution_id: str,
        node_id: str,
        comment: str | None = None,
        decision_option: str | None = None,
    ) -> None:
        if decision_option is not None and str(decision_option).strip():
            self.decide(
                execution_id=execution_id,
                node_id=node_id,
                decision_option=str(decision_option),
                comment=comment,
            )
            return
        self.approve(execution_id=execution_id, node_id=node_id, comment=comment)

    def reject_node(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> None:
        self.reject(
            execution_id=execution_id,
            node_id=node_id,
            fallback_node_id=fallback_node_id,
            comment=comment,
        )

    def submit_node(
        self,
        execution_id: str,
        node_id: str,
        human_input: Mapping[str, Any] | None = None,
        comment: str | None = None,
    ) -> None:
        self.submit(
            execution_id=execution_id,
            node_id=node_id,
            human_input=human_input,
            comment=comment,
        )

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

    def _build_submission_result(self, payload: Mapping[str, Any]) -> str:
        """Build a generic `result` field so downstream ref:<node>.result works.

        Priority:
        1) explicit text fields (text / input_text)
        2) uploaded file text
        3) compact JSON fallback
        """
        for key in ("text", "input_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        file_value = payload.get("file")
        if isinstance(file_value, Mapping):
            file_text = file_value.get("text")
            if isinstance(file_text, str) and file_text.strip():
                return file_text.strip()

        if not payload:
            return ""
        try:
            return json.dumps(dict(payload), ensure_ascii=False, default=str)
        except Exception:
            return str(payload)

    def _get_approval_routes(self, execution_id: str, node_id: str) -> dict[str, Any]:
        node_configs = self._node_configs_by_execution.get(execution_id, {})
        config = node_configs.get(node_id, {})
        routes = config.get("approval_routes")
        if isinstance(routes, dict):
            return dict(routes)
        return {}
