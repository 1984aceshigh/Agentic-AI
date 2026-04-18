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
    ExecutionDetailView,
    ExecutionArtifactsView,
    ExecutionSummaryView,
    GraphView,
    NodeCardView,
    NodeExecutionResultView,
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

    def build_execution_summaries(self, workflow_id: str | None = None) -> list[ExecutionSummaryView]:
        records = self._records_manager.list_workflow_records(workflow_id)
        summaries: list[ExecutionSummaryView] = []
        for record in records:
            waiting_human_count = 0
            failed_count = 0
            for node_record in record.node_records:
                status = self._to_text(node_record.status)
                if status == "WAITING_HUMAN":
                    waiting_human_count += 1
                elif status == "FAILED":
                    failed_count += 1

            summaries.append(
                ExecutionSummaryView(
                    execution_id=record.execution_id,
                    workflow_id=record.workflow_id,
                    status=self._to_text(record.status),
                    started_at=self._format_datetime(record.started_at),
                    finished_at=self._format_datetime(record.finished_at),
                    node_count=len(record.node_records),
                    waiting_human_count=waiting_human_count,
                    failed_count=failed_count,
                )
            )
        return summaries

    def build_execution_detail(self, execution_id: str) -> ExecutionDetailView:
        workflow_record = self._records_manager.get_workflow_record(execution_id)
        node_results: list[NodeExecutionResultView] = []
        waiting_human_count = 0
        failed_count = 0
        for node_record in workflow_record.node_records:
            status = self._to_text(node_record.status)
            if status == "WAITING_HUMAN":
                waiting_human_count += 1
            elif status == "FAILED":
                failed_count += 1

            node_results.append(
                NodeExecutionResultView(
                    node_id=node_record.node_id,
                    node_type=self._to_text(node_record.node_type),
                    status=status,
                    started_at=self._format_datetime(node_record.started_at),
                    finished_at=self._format_datetime(node_record.finished_at),
                    retry_count=node_record.retry_count,
                    error_message=node_record.error_message,
                    output_preview=node_record.output_preview,
                )
            )

        events = self._records_manager.find_events(execution_id)
        return ExecutionDetailView(
            execution_id=workflow_record.execution_id,
            workflow_id=workflow_record.workflow_id,
            status=self._to_text(workflow_record.status),
            started_at=self._format_datetime(workflow_record.started_at),
            finished_at=self._format_datetime(workflow_record.finished_at),
            node_count=len(workflow_record.node_records),
            waiting_human_count=waiting_human_count,
            failed_count=failed_count,
            event_count=len(events),
            node_results=node_results,
        )

    def build_node_cards(
        self,
        graph: GraphModel,
        execution_id: str | None,
    ) -> list[NodeCardView]:
        node_record_map: dict[str, NodeExecutionRecord] = {}
        node_states: dict[str, str] = {}

        if execution_id is not None:
            workflow_record = self._records_manager.get_workflow_record(execution_id)
            context = self._context_manager.get_context(execution_id)
            node_record_map = self._build_node_record_map(workflow_record)
            node_states = context.node_states

        cards: list[NodeCardView] = []
        for node_id, graph_node in graph.nodes.items():
            node_record = node_record_map.get(node_id)
            status = self._resolve_node_status(node_id, node_record, node_states)
            cards.append(
                NodeCardView(
                    node_id=node_id,
                    node_name=graph_node.name,
                    node_type=self._to_text(graph_node.type),
                    task=self._resolve_node_task(graph_node, node_record),
                    status=status,
                    group=graph_node.group,
                    started_at=self._format_datetime(getattr(node_record, "started_at", None)),
                    finished_at=self._format_datetime(getattr(node_record, "finished_at", None)),
                    requires_human_action=self._resolve_requires_human_action(node_record, status),
                    retryable=self._is_retryable(status),
                    error_message=getattr(node_record, "error_message", None),
                    output_preview=getattr(node_record, "output_preview", None),
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
            task=self._resolve_node_task(graph_node, node_record),
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
            memory_count=self._extract_count(
                node_output,
                section_key="memory",
                legacy_items_key="records",
                default=len(memory_records),
            ),
            rag_query_text=self._extract_query_text(node_output),
            rag_hits=rag_hits,
            rag_count=self._extract_count(
                node_output,
                section_key="rag",
                legacy_items_key="hits",
                default=len(rag_hits),
            ),
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

    def _resolve_node_task(
        self,
        graph_node: Any,
        node_record: NodeExecutionRecord | None,
    ) -> str | None:
        config = getattr(graph_node, "config", None)
        if not isinstance(config, dict):
            config = {}

        task = config.get("task")
        if task is not None:
            task_text = self._to_text(task).strip()
            if task_text:
                return task_text

        legacy_type = self._to_text(getattr(node_record, "node_type", "")).strip().lower()
        legacy_task_map = {
            "llm_generate": "generate",
            "llm_review": "assessment",
            "rag_retrieve": "retrieve",
            "deterministic_transform": "transform",
        }
        return legacy_task_map.get(legacy_type)

    def _extract_memory_records(self, node_output: dict[str, Any]) -> list[dict[str, Any]]:
        memory_output = node_output.get("memory")
        if isinstance(memory_output, dict):
            records = memory_output.get("records")
            if isinstance(records, list):
                return [self._json_friendly_dict(record) for record in records]

        records = node_output.get("records")
        if not isinstance(records, list):
            return []
        return [self._json_friendly_dict(record) for record in records]

    def _extract_rag_hits(self, node_output: dict[str, Any]) -> list[dict[str, Any]]:
        rag_output = node_output.get("rag")
        if isinstance(rag_output, dict):
            hits = rag_output.get("hits")
            if isinstance(hits, list):
                return [self._json_friendly_dict(hit) for hit in hits]

        hits = node_output.get("hits")
        if not isinstance(hits, list):
            return []
        return [self._json_friendly_dict(hit) for hit in hits]

    def _extract_query_text(self, node_output: dict[str, Any]) -> str | None:
        rag_output = node_output.get("rag")
        if isinstance(rag_output, dict):
            query_text = rag_output.get("query_text")
            if query_text is not None:
                return self._to_text(query_text)

        query_text = node_output.get("query_text")
        if query_text is None:
            return None
        return self._to_text(query_text)

    def _extract_count(
        self,
        node_output: dict[str, Any],
        *,
        section_key: str,
        legacy_items_key: str,
        default: int,
    ) -> int:
        section_output = node_output.get(section_key)
        if isinstance(section_output, dict):
            section_count = section_output.get("count")
            if isinstance(section_count, int):
                return section_count
            if legacy_items_key in section_output:
                return default

        if legacy_items_key not in node_output:
            return 0
        value = node_output.get("count")
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
        return value.strftime("%Y-%m-%d %H:%M:%S")

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
            return self._format_datetime(value)
        if isinstance(value, Enum):
            return self._to_text(value)
        return deepcopy(value)

    def _to_text(self, value: Any) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        return str(value)
