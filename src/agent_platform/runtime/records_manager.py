from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from agent_platform.models.execution import (
    ExecutionEvent,
    NodeExecutionRecord,
    WorkflowExecutionRecord,
)
from agent_platform.models.profiles import NodeStatus
from agent_platform.runtime.events import (
    EVENT_TYPE_NODE_FAILED,
    EVENT_TYPE_NODE_STARTED,
    EVENT_TYPE_NODE_SUCCEEDED,
    EVENT_TYPE_NODE_WAITING_HUMAN,
    EVENT_TYPE_WORKFLOW_STATUS_CHANGED,
    NODE_STATUS_FAILED,
    NODE_STATUS_RUNNING,
    NODE_STATUS_SUCCEEDED,
    NODE_STATUS_WAITING_HUMAN,
    WORKFLOW_STATUS_RUNNING,
    create_execution_event,
    utc_now,
)


class ExecutionRecordNotFoundError(KeyError):
    """Raised when the requested execution record does not exist."""

    def __init__(self, execution_id: str, node_id: str | None = None) -> None:
        if node_id is None:
            message = f"WorkflowExecutionRecord not found: execution_id={execution_id}"
        else:
            message = (
                "NodeExecutionRecord not found: "
                f"execution_id={execution_id}, node_id={node_id}"
            )
        super().__init__(message)
        self.execution_id = execution_id
        self.node_id = node_id


class ExecutionRecordsManager:
    """In-memory manager for workflow and node execution records."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._workflow_records: dict[str, WorkflowExecutionRecord] = {}
        self._node_records: dict[tuple[str, str], NodeExecutionRecord] = {}
        self._events: dict[str, list[ExecutionEvent]] = {}
        self._storage_path = storage_path
        self._load_state()

    def create_workflow_record(
        self,
        execution_id: str,
        workflow_id: str,
        workflow_version: str | None = None,
    ) -> WorkflowExecutionRecord:
        record = WorkflowExecutionRecord(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            status=_normalize_status(WORKFLOW_STATUS_RUNNING),
            started_at=utc_now(),
            finished_at=None,
            node_records=[],
            summary=None,
        )
        self._workflow_records[execution_id] = record
        self._events.setdefault(execution_id, [])
        self._persist_state()
        return record

    def get_workflow_record(self, execution_id: str) -> WorkflowExecutionRecord:
        record = self._workflow_records.get(execution_id)
        if record is None:
            raise ExecutionRecordNotFoundError(execution_id)
        return record

    def start_node_record(
        self,
        execution_id: str,
        node_id: str,
        node_type: str,
    ) -> NodeExecutionRecord:
        workflow_record = self.get_workflow_record(execution_id)
        key = (execution_id, node_id)
        existing = self._node_records.get(key)

        if existing is None:
            record = NodeExecutionRecord(
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                status=_normalize_status(NODE_STATUS_RUNNING),
                started_at=utc_now(),
                finished_at=None,
                input_preview=None,
                output_preview=None,
                full_input_ref=None,
                full_output_ref=None,
                error_message=None,
                logs=[],
                retry_count=0,
                requires_human_action=False,
                adapter_ref=None,
                contract=None,
                connection_ref=None,
                resolved_capabilities=[],
            )
            self._node_records[key] = record
            workflow_record.node_records.append(record)
        else:
            existing.retry_count += 1
            existing.status = _normalize_status(NODE_STATUS_RUNNING)
            existing.started_at = existing.started_at or utc_now()
            existing.finished_at = None
            existing.error_message = None
            existing.requires_human_action = False
            record = existing

        self.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_NODE_STARTED,
            node_id=node_id,
            message=f"Node started: {node_id}",
        )
        self._persist_state()
        return record

    def complete_node_record(
        self,
        execution_id: str,
        node_id: str,
        output_preview: str | None = None,
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.status = _normalize_status(NODE_STATUS_SUCCEEDED)
        record.finished_at = utc_now()
        record.requires_human_action = False
        if output_preview is not None:
            record.output_preview = output_preview

        self.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_NODE_SUCCEEDED,
            node_id=node_id,
            message=f"Node succeeded: {node_id}",
        )
        self._persist_state()
        return record

    def fail_node_record(
        self,
        execution_id: str,
        node_id: str,
        error_message: str,
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.status = _normalize_status(NODE_STATUS_FAILED)
        record.finished_at = utc_now()
        record.error_message = error_message
        record.requires_human_action = False

        self.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_NODE_FAILED,
            node_id=node_id,
            message=error_message,
        )
        self._persist_state()
        return record

    def mark_node_waiting_human(
        self,
        execution_id: str,
        node_id: str,
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.status = _normalize_status(NODE_STATUS_WAITING_HUMAN)
        record.requires_human_action = True
        record.finished_at = None

        self.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_NODE_WAITING_HUMAN,
            node_id=node_id,
            message=f"Node waiting for human action: {node_id}",
        )
        self._persist_state()
        return record

    def append_node_log(
        self,
        execution_id: str,
        node_id: str,
        message: str,
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.logs.append(message)
        self._persist_state()
        return record

    def set_node_input_preview(
        self,
        execution_id: str,
        node_id: str,
        input_preview: str | None,
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.input_preview = input_preview
        self._persist_state()
        return record

    def set_node_adapter_info(
        self,
        execution_id: str,
        node_id: str,
        adapter_ref: str | None,
        contract: str | None,
        connection_ref: str | None,
        resolved_capabilities: list[str],
    ) -> NodeExecutionRecord:
        record = self.get_node_record(execution_id, node_id)
        record.adapter_ref = adapter_ref
        record.contract = contract
        record.connection_ref = connection_ref
        record.resolved_capabilities = list(resolved_capabilities)
        self._persist_state()
        return record

    def append_event(
        self,
        execution_id: str,
        event_type: str,
        node_id: str | None = None,
        message: str | None = None,
        payload_ref: str | None = None,
    ) -> ExecutionEvent:
        self.get_workflow_record(execution_id)
        event = create_execution_event(
            execution_id=execution_id,
            event_type=event_type,
            node_id=node_id,
            message=message,
            payload_ref=payload_ref,
        )
        self._events.setdefault(execution_id, []).append(event)
        self._persist_state()
        return event

    def set_workflow_status(
        self,
        execution_id: str,
        status: str,
    ) -> WorkflowExecutionRecord:
        record = self.get_workflow_record(execution_id)
        record.status = _normalize_status(status)
        if status in {"SUCCEEDED", "FAILED"}:
            record.finished_at = utc_now()

        self.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_WORKFLOW_STATUS_CHANGED,
            message=f"Workflow status changed to {status}",
        )
        self._persist_state()
        return record

    def get_node_record(
        self,
        execution_id: str,
        node_id: str,
    ) -> NodeExecutionRecord:
        record = self._node_records.get((execution_id, node_id))
        if record is None:
            raise ExecutionRecordNotFoundError(execution_id, node_id)
        return record

    def find_node_records(
        self,
        execution_id: str,
    ) -> list[NodeExecutionRecord]:
        workflow_record = self.get_workflow_record(execution_id)
        return list(workflow_record.node_records)

    def find_events(
        self,
        execution_id: str,
    ) -> list[ExecutionEvent]:
        self.get_workflow_record(execution_id)
        return list(self._events.get(execution_id, []))

    def list_workflow_records(self, workflow_id: str | None = None) -> list[WorkflowExecutionRecord]:
        records = list(self._workflow_records.values())
        if workflow_id is not None:
            records = [record for record in records if record.workflow_id == workflow_id]
        min_dt = datetime.min.replace(tzinfo=timezone.utc)
        records.sort(key=lambda record: record.started_at or min_dt, reverse=True)
        return records

    def _load_state(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return

        loaded = json.loads(self._storage_path.read_text(encoding="utf-8"))
        workflow_payloads = loaded.get("workflow_records", []) if isinstance(loaded, dict) else []
        event_payloads = loaded.get("events", {}) if isinstance(loaded, dict) else {}

        if not isinstance(workflow_payloads, list):
            workflow_payloads = []
        if not isinstance(event_payloads, dict):
            event_payloads = {}

        for item in workflow_payloads:
            record = WorkflowExecutionRecord.model_validate(item)
            self._workflow_records[record.execution_id] = record
            self._events.setdefault(record.execution_id, [])
            for node_record in record.node_records:
                key = (record.execution_id, node_record.node_id)
                self._node_records[key] = node_record

        for execution_id, items in event_payloads.items():
            if not isinstance(execution_id, str) or not isinstance(items, list):
                continue
            self._events[execution_id] = [ExecutionEvent.model_validate(event) for event in items]

    def _persist_state(self) -> None:
        if self._storage_path is None:
            return

        workflow_records = [
            _normalize_workflow_record_for_dump(record)
            for record in self._workflow_records.values()
        ]
        payload = {
            "workflow_records": [record.model_dump(mode="json") for record in workflow_records],
            "events": {
                execution_id: [event.model_dump(mode="json") for event in events]
                for execution_id, events in self._events.items()
            },
        }

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_status(status: str | NodeStatus) -> NodeStatus | str:
    if isinstance(status, NodeStatus):
        return status
    try:
        return NodeStatus(str(status))
    except ValueError:
        return str(status)


def _normalize_workflow_record_for_dump(record: WorkflowExecutionRecord) -> WorkflowExecutionRecord:
    normalized = record.model_copy(deep=True)
    normalized.status = _normalize_status(normalized.status)
    for node_record in normalized.node_records:
        node_record.status = _normalize_status(node_record.status)
    return normalized
