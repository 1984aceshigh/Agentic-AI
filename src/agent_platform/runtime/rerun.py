from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

try:
    from agent_platform.runtime.events import NODE_STATUS_PENDING
except Exception:  # pragma: no cover - fallback for partial project imports
    NODE_STATUS_PENDING = "PENDING"


WORKFLOW_STATUS_RERUNNING = "RERUNNING"
EVENT_TYPE_RERUN_PREPARED = "rerun_prepared"


class RerunService:
    """Prepare runtime state for rerunning from a target node.

    This service does not resume LangGraph directly. It only invalidates the
    runtime state and execution records from the specified node onward so that
    the caller can start execution again from a clean downstream state.
    """

    def __init__(self, context_manager: Any, records_manager: Any) -> None:
        self._context_manager = context_manager
        self._records_manager = records_manager

    def prepare_rerun(self, execution_id: str, graph: Any, from_node_id: str) -> Any:
        context = self._context_manager.get_context(execution_id)
        downstream_node_ids = self.collect_downstream_nodes(graph, from_node_id)

        for node_id in downstream_node_ids:
            context.node_states[node_id] = NODE_STATUS_PENDING
            context.node_outputs.pop(node_id, None)

        self._context_manager.save_context(context)

        workflow_record = self._records_manager.get_workflow_record(execution_id)
        node_records = list(getattr(workflow_record, "node_records", []) or [])
        for record in node_records:
            node_id = getattr(record, "node_id", None)
            if node_id in downstream_node_ids:
                self._reset_node_record(record)

        self._set_workflow_status(execution_id, WORKFLOW_STATUS_RERUNNING)

        event = self._records_manager.append_event(
            execution_id=execution_id,
            event_type=EVENT_TYPE_RERUN_PREPARED,
            node_id=from_node_id,
            message=(
                f"Rerun prepared from {from_node_id}. "
                f"Affected nodes: {', '.join(downstream_node_ids)}"
            ),
            payload_ref=from_node_id,
        )

        append_event = getattr(self._context_manager, "append_event", None)
        if callable(append_event):
            append_event(execution_id, event)

        return context

    def collect_downstream_nodes(self, graph: Any, from_node_id: str) -> list[str]:
        node_ids = self._extract_graph_node_ids(graph)
        if node_ids and from_node_id not in node_ids:
            raise ValueError(f"from_node_id is not present in graph: {from_node_id}")

        adjacency = self._build_adjacency(graph)
        visited: set[str] = set()
        ordered: list[str] = []
        queue: deque[str] = deque([from_node_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            ordered.append(current)
            for next_node_id in adjacency.get(current, []):
                if next_node_id not in visited:
                    queue.append(next_node_id)

        return ordered

    def _set_workflow_status(self, execution_id: str, status: str) -> None:
        set_workflow_status = getattr(self._records_manager, "set_workflow_status", None)
        if callable(set_workflow_status):
            set_workflow_status(execution_id, status)
            return

        workflow_record = self._records_manager.get_workflow_record(execution_id)
        workflow_record.status = status

    def _reset_node_record(self, record: Any) -> None:
        record.status = NODE_STATUS_PENDING
        if hasattr(record, "started_at"):
            record.started_at = None
        if hasattr(record, "finished_at"):
            record.finished_at = None
        if hasattr(record, "error_message"):
            record.error_message = None
        if hasattr(record, "requires_human_action"):
            record.requires_human_action = False
        if hasattr(record, "output_preview"):
            record.output_preview = None
        if hasattr(record, "full_output_ref"):
            record.full_output_ref = None
        if hasattr(record, "logs") and isinstance(record.logs, list):
            record.logs.clear()

    def _extract_graph_node_ids(self, graph: Any) -> set[str]:
        raw_nodes = getattr(graph, "nodes", None)
        if raw_nodes is None and isinstance(graph, Mapping):
            raw_nodes = graph.get("nodes")

        node_ids: set[str] = set()
        for node in raw_nodes or []:
            node_id = self._extract_node_id(node)
            if node_id:
                node_ids.add(node_id)
        return node_ids

    def _build_adjacency(self, graph: Any) -> dict[str, list[str]]:
        raw_edges = getattr(graph, "edges", None)
        if raw_edges is None and isinstance(graph, Mapping):
            raw_edges = graph.get("edges")

        adjacency: dict[str, list[str]] = {}
        for edge in raw_edges or []:
            src, dst = self._extract_edge_endpoints(edge)
            if not src or not dst:
                continue
            adjacency.setdefault(src, [])
            if dst not in adjacency[src]:
                adjacency[src].append(dst)
        return adjacency

    def _extract_node_id(self, node: Any) -> str | None:
        if isinstance(node, Mapping):
            value = node.get("id") or node.get("node_id")
            return str(value) if value else None

        for attr in ("id", "node_id"):
            value = getattr(node, attr, None)
            if value:
                return str(value)
        return None

    def _extract_edge_endpoints(self, edge: Any) -> tuple[str | None, str | None]:
        if isinstance(edge, Mapping):
            src = edge.get("from") or edge.get("source") or edge.get("from_node_id")
            dst = edge.get("to") or edge.get("target") or edge.get("to_node_id")
            return (str(src) if src else None, str(dst) if dst else None)

        src = (
            getattr(edge, "from_", None)
            or getattr(edge, "from_node_id", None)
            or getattr(edge, "source", None)
            or getattr(edge, "from", None)
        )
        dst = (
            getattr(edge, "to", None)
            or getattr(edge, "to_node_id", None)
            or getattr(edge, "target", None)
        )
        return (str(src) if src else None, str(dst) if dst else None)
