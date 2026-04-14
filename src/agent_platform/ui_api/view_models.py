from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowSummaryView(_BaseViewModel):
    workflow_id: str
    workflow_name: str
    last_execution_id: str | None = None
    last_status: str | None = None
    last_updated_at: str | None = None
    waiting_human_count: int = 0
    failed_count: int = 0


class NodeCardView(_BaseViewModel):
    node_id: str
    node_name: str
    node_type: str
    status: str
    group: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    requires_human_action: bool = False
    retryable: bool = False
    error_message: str | None = None


class NodeDetailView(_BaseViewModel):
    node_id: str
    node_name: str
    node_type: str
    status: str
    input_preview: str | None = None
    output_preview: str | None = None
    logs: list[str] = Field(default_factory=list)
    error_message: str | None = None
    adapter_ref: str | None = None
    contract: str | None = None
    connection_ref: str | None = None
    resolved_capabilities: list[str] = Field(default_factory=list)
    memory_records: list[dict[str, Any]] = Field(default_factory=list)
    memory_count: int = 0
    rag_query_text: str | None = None
    rag_hits: list[dict[str, Any]] = Field(default_factory=list)
    rag_count: int = 0
    event_history: list[dict[str, Any]] = Field(default_factory=list)


class GraphView(_BaseViewModel):
    workflow_id: str
    workflow_name: str
    mermaid_text: str


class ExecutionArtifactsView(_BaseViewModel):
    execution_id: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
