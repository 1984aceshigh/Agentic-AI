from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .profiles import NodeStatus


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_type: str
    timestamp: datetime
    execution_id: str
    node_id: str | None = None
    message: str | None = None
    payload_ref: str | None = None


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    execution_id: str
    workflow_id: str
    workflow_version: str | None = None
    global_inputs: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    node_states: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    events: list[ExecutionEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    execution_id: str
    node_id: str
    node_type: str
    status: NodeStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input_preview: str | None = None
    output_preview: str | None = None
    full_input_ref: str | None = None
    full_output_ref: str | None = None
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
    retry_count: int = 0
    requires_human_action: bool = False
    adapter_ref: str | None = None
    contract: str | None = None
    connection_ref: str | None = None
    resolved_capabilities: list[str] = Field(default_factory=list)


class WorkflowExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    execution_id: str
    workflow_id: str
    workflow_version: str | None = None
    status: NodeStatus | str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    node_records: list[NodeExecutionRecord] = Field(default_factory=list)
    summary: str | None = None
