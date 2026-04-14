from __future__ import annotations

from datetime import datetime, timezone

from agent_platform.models.execution import ExecutionEvent


EVENT_TYPE_NODE_STARTED = "node_started"
EVENT_TYPE_NODE_SUCCEEDED = "node_succeeded"
EVENT_TYPE_NODE_FAILED = "node_failed"
EVENT_TYPE_NODE_WAITING_HUMAN = "node_waiting_human"
EVENT_TYPE_WORKFLOW_STATUS_CHANGED = "workflow_status_changed"


NODE_STATUS_PENDING = "PENDING"
NODE_STATUS_RUNNING = "RUNNING"
NODE_STATUS_SUCCEEDED = "SUCCEEDED"
NODE_STATUS_FAILED = "FAILED"
NODE_STATUS_WAITING_HUMAN = "WAITING_HUMAN"
NODE_STATUS_SKIPPED = "SKIPPED"


WORKFLOW_STATUS_PENDING = "PENDING"
WORKFLOW_STATUS_RUNNING = "RUNNING"
WORKFLOW_STATUS_SUCCEEDED = "SUCCEEDED"
WORKFLOW_STATUS_FAILED = "FAILED"
WORKFLOW_STATUS_WAITING_HUMAN = "WAITING_HUMAN"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_execution_event(
    execution_id: str,
    event_type: str,
    node_id: str | None = None,
    message: str | None = None,
    payload_ref: str | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_type=event_type,
        timestamp=utc_now(),
        execution_id=execution_id,
        node_id=node_id,
        message=message,
        payload_ref=payload_ref,
    )
