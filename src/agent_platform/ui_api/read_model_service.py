from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import Any

from agent_platform.graph import build_mermaid
from agent_platform.models import ExecutionEvent, GraphModel, NodeExecutionRecord, WorkflowExecutionRecord
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.records_manager import ExecutionRecordsManager

from .view_models import (
    ExecutionArtifactsView,
    GraphView,
    NodeCardView,
    NodeDetailView,
    WorkflowSummaryView,
)


class ReadModelService:
    """Builds UI-facing read models from runtime state and execution records."""

    def __init__(
        self,
        context_manager: ExecutionContextManager,
        records_manager: ExecutionRecordsManager,
    ) -> None:
        self._context_manager = context_manager
        self._records_manager = records_manager

    def build_workflow_summary(
        self,
        graph: GraphModel,
        execution_id: str | None = None,
    ) -> WorkflowSummaryView:
        if execution_id is None:
            return WorkflowSummaryView(
                workflow_id=graph.workflow_id,
                workflow_name=graph.workflow_name,
            )

        workflow_record = self._records_manager.get_workflow_record(execution_id)
        waiting_human_count = 0
        failed_count = 0
        for node_record in workflow_record.node_records:
            status = self._to_text(node_record.status)
            if status == "WAITING_HUMAN":
                waiting_human_count += 1
            elif status == "FAILED":
                failed_count += 1

        # MVPでは workflow-level の「最終更新日時」の意味がまだ固定されていない。
        # started_at / finished_at から推定するとテストや今後のUI要件とずれやすいため、
        # 専用の更新時刻が整備されるまでは未設定として扱う。
        last_updated_at = None

        return WorkflowSummaryView(
            workflow_id=graph.workflow_id,
            workflow_name=graph.workflow_name,
            last_execution_id=workflow_record.execution_id,
            last_status=self._to_text(workflow_record.status),
            last_updated_at=last_updated_at,
            waiting_human_count=waiting_human_count,
            failed_count=failed_count,
        )

    def build_node_cards(
        self,
        graph: GraphModel,
        execution_id: str,
    ) -> list[NodeCardView]:
        workflow_record = self._records_manager.get_workflow_record(execution_id)
        context = self._context_manager.get_context(execution_id)
        node_record_map = self._build_node_record_map(workflow_record)

        cards: list[NodeCardView] = []
        for node_id, graph_node in graph.nodes.items():
            node_record = node_record_map.get(node_id)
            status = self._resolve_node_status(node_id, node_record, context.node_states)
            cards.append(
                NodeCardView(
                    node_id=node_id,
                    node_name=graph_node.name,
                    node_type=self._to_text(graph_node.type),
                    status=status,
                    group=graph_node.group,
                    started_at=self._format_datetime(getattr(node_record, "started_at", None)),
                    finished_at=self._format_datetime(getattr(node_record, "finished_at", None)),
                    requires_human_action=self._resolve_requires_human_action(node_record, status),
                    retryable=self._is_retryable(status),
                    error_message=getattr(node_record, "error_message", None),
                )
            )
        return cards

    def build_node_detail(
        self,
        graph: GraphModel,
        execution_id: str,
        node_id: str,
    ) -> NodeDetailView:
        if node_id not in graph.nodes:
            raise KeyError(f"Unknown node_id: {node_id}")

        workflow_record = self._records_manager.get_workflow_record(execution_id)
        context = self._context_manager.get_context(execution_id)
        graph_node = graph.nodes[node_id]
        node_record = self._build_node_record_map(workflow_record).get(node_id)
        node_output = context.node_outputs.get(node_id, {})
        status = self._resolve_node_status(node_id, node_record, context.node_states)

        memory_records = self._extract_memory_records(node_output)
        rag_hits = self._extract_rag_hits(node_output)

        return NodeDetailView(
            node_id=node_id,
            node_name=graph_node.name,
            node_type=self._to_text(graph_node.type),
            status=status,
            input_preview=getattr(node_record, "input_preview", None),
            output_preview=getattr(node_record, "output_preview", None),
            logs=list(getattr(node_record, "logs", []) or []),
            error_message=getattr(node_record, "error_message", None),
            adapter_ref=getattr(node_record, "adapter_ref", None),
            contract=getattr(node_record, "contract", None),
            connection_ref=getattr(node_record, "connection_ref", None),
            resolved_capabilities=list(getattr(node_record, "resolved_capabilities", []) or []),
            memory_records=memory_records,
            memory_count=self._extract_count(node_output, "count", default=len(memory_records), for_key="records"),
            rag_query_text=self._extract_query_text(node_output),
            rag_hits=rag_hits,
            rag_count=self._extract_count(node_output, "count", default=len(rag_hits), for_key="hits"),
            event_history=self._collect_event_history(context.events, node_id),
        )

    def build_graph_view(self, graph: GraphModel) -> GraphView:
        return GraphView(
            workflow_id=graph.workflow_id,
            workflow_name=graph.workflow_name,
            mermaid_text=build_mermaid(graph),
        )

    def build_execution_artifacts_view(self, execution_id: str) -> ExecutionArtifactsView:
        context = self._context_manager.get_context(execution_id)
        return ExecutionArtifactsView(
            execution_id=context.execution_id,
            artifacts=self._json_friendly_dict(context.artifacts),
            node_outputs=self._json_friendly_dict(context.node_outputs),
        )

    def _build_node_record_map(
        self,
        workflow_record: WorkflowExecutionRecord,
    ) -> dict[str, NodeExecutionRecord]:
        return {node_record.node_id: node_record for node_record in workflow_record.node_records}

    def _resolve_node_status(
        self,
        node_id: str,
        node_record: NodeExecutionRecord | None,
        node_states: dict[str, str],
    ) -> str:
        if node_record is not None:
            return self._to_text(node_record.status)
        return self._to_text(node_states.get(node_id, "PENDING"))

    def _resolve_requires_human_action(
        self,
        node_record: NodeExecutionRecord | None,
        status: str,
    ) -> bool:
        if node_record is not None:
            return bool(node_record.requires_human_action)
        return status == "WAITING_HUMAN"

    def _extract_memory_records(self, node_output: dict[str, Any]) -> list[dict[str, Any]]:
        records = node_output.get("records")
        if not isinstance(records, list):
            return []
        return [self._json_friendly_dict(record) for record in records]

    def _extract_rag_hits(self, node_output: dict[str, Any]) -> list[dict[str, Any]]:
        hits = node_output.get("hits")
        if not isinstance(hits, list):
            return []
        return [self._json_friendly_dict(hit) for hit in hits]

    def _extract_query_text(self, node_output: dict[str, Any]) -> str | None:
        query_text = node_output.get("query_text")
        if query_text is None:
            return None
        return self._to_text(query_text)

    def _extract_count(
        self,
        node_output: dict[str, Any],
        key: str,
        *,
        default: int,
        for_key: str,
    ) -> int:
        if for_key not in node_output:
            return 0
        value = node_output.get(key)
        if isinstance(value, int):
            return value
        return default

    def _collect_event_history(
        self,
        events: list[ExecutionEvent],
        node_id: str,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for event in events:
            if event.node_id != node_id:
                continue
            history.append(
                {
                    "event_type": self._to_text(event.event_type),
                    "timestamp": self._format_datetime(event.timestamp),
                    "execution_id": event.execution_id,
                    "node_id": event.node_id,
                    "message": event.message,
                    "payload_ref": event.payload_ref,
                }
            )
        return history

    def _is_retryable(self, status: str) -> bool:
        return status in {"FAILED", "WAITING_HUMAN", "SUCCEEDED", "SKIPPED"}

    def _format_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _json_friendly_dict(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            dumped = value.model_dump(mode="python")
            return self._json_friendly_dict(dumped)
        if isinstance(value, dict):
            return {str(key): self._json_friendly_dict(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_friendly_dict(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_friendly_dict(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return self._to_text(value)
        return deepcopy(value)

    def _to_text(self, value: Any) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return str(value)
