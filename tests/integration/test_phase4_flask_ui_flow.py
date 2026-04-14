from __future__ import annotations

from datetime import datetime, timezone

from agent_platform.models import ExecutionEvent, GraphEdge, GraphModel, GraphNode
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.records_manager import ExecutionRecordsManager
from agent_platform.ui_api import ReadModelService, create_app, set_latest_execution_ids, set_workflow_graphs

UTC = timezone.utc


class StatefulHumanGateService:
    def __init__(
        self,
        context_manager: ExecutionContextManager,
        records_manager: ExecutionRecordsManager,
    ) -> None:
        self._context_manager = context_manager
        self._records_manager = records_manager
        self.approvals: list[dict[str, str | None]] = []
        self.rejections: list[dict[str, str | None]] = []
        self.valid_execution_ids: set[str] = set()
        self.valid_node_ids: set[str] = set()

    def approve_node(
        self,
        execution_id: str,
        node_id: str,
        comment: str | None = None,
    ) -> None:
        self._ensure_known(execution_id, node_id)
        self.approvals.append(
            {"execution_id": execution_id, "node_id": node_id, "comment": comment}
        )
        self._records_manager.complete_node_record(
            execution_id,
            node_id,
            output_preview="approved via ui",
        )
        self._records_manager.append_node_log(execution_id, node_id, "approved via ui")
        self._context_manager.update_node_state(execution_id, node_id, "SUCCEEDED")

    def reject_node(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> None:
        self._ensure_known(execution_id, node_id)
        self.rejections.append(
            {
                "execution_id": execution_id,
                "node_id": node_id,
                "fallback_node_id": fallback_node_id,
                "comment": comment,
            }
        )
        self._records_manager.append_node_log(execution_id, node_id, "rejected via ui")
        if fallback_node_id:
            self._context_manager.update_node_state(execution_id, fallback_node_id, "PENDING")
            self._context_manager.append_event(
                execution_id,
                ExecutionEvent(
                    event_type="node_rejected",
                    timestamp=datetime(2026, 4, 12, 2, 3, 30, tzinfo=UTC),
                    execution_id=execution_id,
                    node_id=node_id,
                    message=f"rejected; fallback to {fallback_node_id}",
                ),
            )

    def _ensure_known(self, execution_id: str, node_id: str) -> None:
        if execution_id not in self.valid_execution_ids or node_id not in self.valid_node_ids:
            raise KeyError("Unknown execution or node")


class StatefulRerunService:
    def __init__(
        self,
        context_manager: ExecutionContextManager,
        records_manager: ExecutionRecordsManager,
        graph: GraphModel,
    ) -> None:
        self._context_manager = context_manager
        self._records_manager = records_manager
        self._graph = graph
        self.calls: list[dict[str, str]] = []
        self.valid_execution_ids: set[str] = set()
        self.valid_node_ids: set[str] = set()

    def rerun_from_node(self, execution_id: str, from_node_id: str) -> None:
        if execution_id not in self.valid_execution_ids or from_node_id not in self.valid_node_ids:
            raise KeyError("Unknown execution or node")

        self.calls.append({"execution_id": execution_id, "from_node_id": from_node_id})
        node_type = self._graph.nodes[from_node_id].type
        record = self._records_manager.start_node_record(execution_id, from_node_id, node_type)
        record.started_at = datetime(2026, 4, 12, 2, 4, tzinfo=UTC)
        record.input_preview = "rerun requested"
        self._records_manager.append_node_log(execution_id, from_node_id, "rerun requested from ui")
        self._context_manager.update_node_state(execution_id, from_node_id, "RUNNING")
        self._records_manager.set_workflow_status(execution_id, "RUNNING")


def make_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step3"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm_generate", name="Draft", group="analysis"),
            "step2": GraphNode(id="step2", type="human_gate", name="Human Review", group="review"),
            "step3": GraphNode(id="step3", type="rag_retrieve", name="Knowledge Lookup", group="review"),
        },
        edges=[
            GraphEdge(from_node="step1", to_node="step2"),
            GraphEdge(from_node="step2", to_node="step3"),
        ],
    )


def build_integration_client():
    graph = make_graph_model()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    read_model_service = ReadModelService(
        context_manager=context_manager,
        records_manager=records_manager,
    )

    context = context_manager.create_context(workflow_id=graph.workflow_id)
    execution_id = context.execution_id
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id=graph.workflow_id)

    draft_record = records_manager.start_node_record(execution_id, "step1", "llm_generate")
    draft_record.started_at = datetime(2026, 4, 12, 2, 0, tzinfo=UTC)
    draft_record.input_preview = "user request"
    records_manager.complete_node_record(execution_id, "step1", output_preview="draft output")

    review_record = records_manager.start_node_record(execution_id, "step2", "human_gate")
    review_record.started_at = datetime(2026, 4, 12, 2, 1, tzinfo=UTC)
    review_record.input_preview = "review draft"
    review_record.output_preview = "awaiting approval"
    records_manager.mark_node_waiting_human(execution_id, "step2")
    records_manager.append_node_log(execution_id, "step2", "waiting for approval")
    records_manager.set_node_adapter_info(
        execution_id,
        "step2",
        adapter_ref="human_gate_internal",
        contract="human_gate",
        connection_ref="LOCAL_UI",
        resolved_capabilities=["approve", "reject"],
    )
    context_manager.set_node_output(
        execution_id,
        "step2",
        {
            "records": [
                {"record_id": "mem-1", "scope": "workflow", "text": "previous memo"},
            ],
            "count": 1,
        },
    )
    context_manager.append_event(
        execution_id,
        ExecutionEvent(
            event_type="node_waiting_human",
            timestamp=datetime(2026, 4, 12, 2, 1, 30, tzinfo=UTC),
            execution_id=execution_id,
            node_id="step2",
            message="approval required",
        ),
    )

    rag_record = records_manager.start_node_record(execution_id, "step3", "rag_retrieve")
    rag_record.started_at = datetime(2026, 4, 12, 2, 2, tzinfo=UTC)
    rag_record.input_preview = "query text"
    records_manager.fail_node_record(execution_id, "step3", error_message="retrieval failed")

    context_manager.update_node_state(execution_id, "step1", "SUCCEEDED")
    context_manager.update_node_state(execution_id, "step2", "WAITING_HUMAN")
    context_manager.update_node_state(execution_id, "step3", "FAILED")
    context_manager.set_node_output(
        execution_id,
        "step3",
        {
            "hits": [
                {
                    "chunk_id": "doc-1",
                    "score": 0.9,
                    "text": "sample chunk",
                    "metadata": {"source": "kb/risk.md"},
                }
            ],
            "count": 1,
            "query_text": "sample query",
        },
    )
    records_manager.set_workflow_status(execution_id, "FAILED")

    human_gate_service = StatefulHumanGateService(context_manager, records_manager)
    rerun_service = StatefulRerunService(context_manager, records_manager, graph)
    human_gate_service.valid_execution_ids.add(execution_id)
    human_gate_service.valid_node_ids.update(graph.nodes.keys())
    rerun_service.valid_execution_ids.add(execution_id)
    rerun_service.valid_node_ids.update(graph.nodes.keys())

    app = create_app(
        read_model_service=read_model_service,
        human_gate_service=human_gate_service,
        rerun_service=rerun_service,
    )
    app.testing = True
    set_workflow_graphs(app, {graph.workflow_id: graph})
    set_latest_execution_ids(app, {graph.workflow_id: execution_id})

    return app.test_client(), execution_id, human_gate_service, rerun_service


def test_phase4_flask_ui_flow_node_list_to_detail() -> None:
    client, execution_id, _, _ = build_integration_client()

    node_list_response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes"
    )

    assert node_list_response.status_code == 200
    assert b"Node List" in node_list_response.data
    assert b"Human Review" in node_list_response.data
    assert (
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/step2".encode()
        in node_list_response.data
    )

    detail_response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/step2"
    )

    assert detail_response.status_code == 200
    assert b"Node Detail" in detail_response.data
    assert b"review draft" in detail_response.data
    assert b"awaiting approval" in detail_response.data
    assert b"waiting for approval" in detail_response.data



def test_phase4_flask_ui_flow_approve_waiting_human_node_updates_status() -> None:
    client, execution_id, human_gate_service, _ = build_integration_client()

    approve_response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/nodes/step2/approve",
        data={
            "comment": "approved from integration",
            "next": f"/workflows/sample_workflow/executions/{execution_id}/nodes?status=waiting_human",
        },
        follow_redirects=False,
    )

    assert approve_response.status_code == 302
    assert human_gate_service.approvals[0]["comment"] == "approved from integration"

    detail_response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/step2"
    )

    assert detail_response.status_code == 200
    assert b"status:</strong> SUCCEEDED" in detail_response.data
    assert b"approved via ui" in detail_response.data



def test_phase4_flask_ui_flow_reject_waiting_human_node_redirects() -> None:
    client, execution_id, human_gate_service, _ = build_integration_client()

    reject_response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/nodes/step2/reject",
        data={
            "fallback_node_id": "step1",
            "comment": "redo from integration",
            "next": f"/workflows/sample_workflow/executions/{execution_id}/nodes?status=waiting_human",
        },
        follow_redirects=True,
    )

    assert reject_response.status_code == 200
    assert human_gate_service.rejections[0]["fallback_node_id"] == "step1"
    assert b"Node List" in reject_response.data



def test_phase4_flask_ui_flow_rerun_failed_node_changes_node_to_running() -> None:
    client, execution_id, _, rerun_service = build_integration_client()

    rerun_response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/rerun",
        json={"from_node_id": "step3"},
    )

    assert rerun_response.status_code == 200
    assert rerun_response.get_json() == {
        "status": "ok",
        "action": "rerun",
        "from_node_id": "step3",
    }
    assert rerun_service.calls[0]["from_node_id"] == "step3"

    node_list_response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes"
    )

    assert node_list_response.status_code == 200
    assert b"Knowledge Lookup" in node_list_response.data
    assert b">RUNNING<" in node_list_response.data



def test_phase4_flask_ui_flow_graph_view_displays_mermaid_and_node_list_link() -> None:
    client, execution_id, _, _ = build_integration_client()

    response = client.get("/workflows/sample_workflow/graph")

    assert response.status_code == 200
    assert b"Graph View" in response.data
    assert b"Sample Workflow" in response.data
    assert b"flowchart TD" in response.data
    assert (
        f"/workflows/sample_workflow/executions/{execution_id}/nodes".encode()
        in response.data
    )
