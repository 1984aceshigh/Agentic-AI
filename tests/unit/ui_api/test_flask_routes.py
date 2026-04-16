from __future__ import annotations

from datetime import datetime, timezone

from agent_platform.models import ExecutionEvent, GraphEdge, GraphModel, GraphNode
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.records_manager import ExecutionRecordsManager
from agent_platform.ui_api import GraphView, ReadModelService, create_app, set_latest_execution_ids, set_workflow_graphs


UTC = timezone.utc


class FakeHumanGateService:
    def __init__(self) -> None:
        self.approvals: list[dict[str, str | None]] = []
        self.rejections: list[dict[str, str | None]] = []
        self.valid_execution_ids: set[str] = set()
        self.valid_node_ids: set[str] = set()

    def approve_node(self, execution_id: str, node_id: str, comment: str | None = None) -> None:
        self._ensure_known(execution_id, node_id)
        self.approvals.append(
            {"execution_id": execution_id, "node_id": node_id, "comment": comment}
        )

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

    def _ensure_known(self, execution_id: str, node_id: str) -> None:
        if execution_id not in self.valid_execution_ids or node_id not in self.valid_node_ids:
            raise KeyError("Unknown execution or node")


class FakeRerunService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.valid_execution_ids: set[str] = set()
        self.valid_node_ids: set[str] = set()

    def rerun_from_node(self, execution_id: str, from_node_id: str) -> None:
        if execution_id not in self.valid_execution_ids or from_node_id not in self.valid_node_ids:
            raise KeyError("Unknown execution or node")
        self.calls.append({"execution_id": execution_id, "from_node_id": from_node_id})


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


def build_test_client():
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

    human_gate_service = FakeHumanGateService()
    rerun_service = FakeRerunService()
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


def test_get_workflows_returns_200() -> None:
    client, _, _, _ = build_test_client()

    response = client.get("/workflows")

    assert response.status_code == 200
    assert b"Workflows" in response.data
    assert b"Sample Workflow" in response.data
    assert b"/actions/workflows/sample_workflow/run" in response.data
    assert b">Run<" in response.data
    assert b"/workflows/sample_workflow/nodes" in response.data
    assert b">Nodes<" in response.data


def test_get_node_list_returns_200() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(f"/workflows/sample_workflow/executions/{execution_id}/nodes")

    assert response.status_code == 200
    assert b"Node List" in response.data
    assert b"Human Review" in response.data
    assert b"2026-04-12T02:01:00+00:00" in response.data
    assert b"Output" in response.data
    assert b"awaiting approval" in response.data


def test_get_node_list_latest_without_execution_returns_pending_cards() -> None:
    graph = make_graph_model()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    read_model_service = ReadModelService(
        context_manager=context_manager,
        records_manager=records_manager,
    )

    app = create_app(
        read_model_service=read_model_service,
        human_gate_service=FakeHumanGateService(),
        rerun_service=FakeRerunService(),
    )
    app.testing = True
    set_workflow_graphs(app, {graph.workflow_id: graph})
    set_latest_execution_ids(app, {graph.workflow_id: None})
    client = app.test_client()

    workflow_response = client.get("/workflows")
    assert workflow_response.status_code == 200
    assert b"/workflows/sample_workflow/nodes" in workflow_response.data

    node_list_response = client.get("/workflows/sample_workflow/nodes")
    assert node_list_response.status_code == 200
    assert b"execution_id: N/A" in node_list_response.data
    assert b">PENDING<" in node_list_response.data
    assert b"disabled>Detail<" in node_list_response.data


def test_node_list_includes_waiting_human_and_failed_action_forms() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(f"/workflows/sample_workflow/executions/{execution_id}/nodes")

    assert response.status_code == 200
    assert b"Approve" in response.data
    assert b"Reject" in response.data
    assert b"Rerun" in response.data


def test_node_list_status_filter_shows_only_requested_status() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes?status=failed"
    )

    assert response.status_code == 200
    assert b"Knowledge Lookup" in response.data
    assert b"Human Review" not in response.data
    assert b"filtered by FAILED" in response.data


def test_get_node_detail_returns_200() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/step2"
    )

    assert response.status_code == 200
    assert b"Node Detail" in response.data
    assert b"Adapter Information" in response.data
    assert b"human_gate_internal" in response.data
    assert b"Memory Results" in response.data
    assert b"previous memo" in response.data
    assert b"Event History" in response.data
    assert b"approval required" in response.data
    assert b"waiting for approval" in response.data


def test_get_node_detail_renders_rag_results() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/step3"
    )

    assert response.status_code == 200
    assert b"RAG Results" in response.data
    assert b"sample query" in response.data
    assert b"sample chunk" in response.data
    assert b"kb/risk.md" in response.data
    assert b"retrieval failed" in response.data


def test_get_graph_view_returns_200() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get("/workflows/sample_workflow/graph")

    assert response.status_code == 200
    assert b"Graph View" in response.data
    assert b"Sample Workflow" in response.data
    assert b"flowchart TD" in response.data
    assert b'class="mermaid"' in response.data
    assert (
        f"/workflows/sample_workflow/executions/{execution_id}/nodes".encode()
        in response.data
    )
    assert b"/actions/workflows/sample_workflow/run" in response.data
    assert b">Run<" in response.data
    assert b"mermaid_init.js" in response.data


def test_graph_view_shows_fallback_when_mermaid_text_missing() -> None:
    graph = make_graph_model()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    read_model_service = ReadModelService(
        context_manager=context_manager,
        records_manager=records_manager,
    )
    read_model_service.build_graph_view = lambda _graph: GraphView(  # type: ignore[method-assign]
        workflow_id=_graph.workflow_id,
        workflow_name=_graph.workflow_name,
        mermaid_text="",
    )

    app = create_app(
        read_model_service=read_model_service,
        human_gate_service=FakeHumanGateService(),
        rerun_service=FakeRerunService(),
    )
    app.testing = True
    set_workflow_graphs(app, {graph.workflow_id: graph})
    set_latest_execution_ids(app, {graph.workflow_id: None})
    client = app.test_client()

    response = client.get("/workflows/sample_workflow/graph")

    assert response.status_code == 200
    assert b"Mermaid graph could not be rendered" in response.data
    assert b"No mermaid_text available." in response.data
    assert b"No execution available for node list." in response.data


def test_post_approve_returns_200_and_json() -> None:
    client, execution_id, human_gate_service, _ = build_test_client()

    response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/nodes/step2/approve",
        json={"comment": "looks good"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "action": "approve", "node_id": "step2"}
    assert human_gate_service.approvals[0]["comment"] == "looks good"


def test_post_reject_returns_200_and_json() -> None:
    client, execution_id, human_gate_service, _ = build_test_client()

    response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/nodes/step2/reject",
        data={"fallback_node_id": "step1", "comment": "redo"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "action": "reject",
        "node_id": "step2",
        "fallback_node_id": "step1",
    }
    assert human_gate_service.rejections[0]["fallback_node_id"] == "step1"


def test_post_rerun_returns_200_and_json() -> None:
    client, execution_id, _, rerun_service = build_test_client()

    response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/rerun",
        json={"from_node_id": "step3"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "action": "rerun",
        "from_node_id": "step3",
    }
    assert rerun_service.calls[0]["from_node_id"] == "step3"


def test_post_run_returns_200_and_json() -> None:
    client, _, _, _ = build_test_client()

    response = client.post(
        "/actions/workflows/sample_workflow/run",
        json={"global_inputs": {"topic": "qa"}},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["action"] == "run"
    assert payload["workflow_id"] == "sample_workflow"
    assert isinstance(payload["execution_id"], str)
    assert payload["execution_id"]


def test_form_post_run_redirects_to_new_execution_node_list() -> None:
    client, _, _, _ = build_test_client()

    response = client.post(
        "/actions/workflows/sample_workflow/run",
        data={"next": "/workflows/sample_workflow/executions/{execution_id}/nodes"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/workflows/sample_workflow/executions/" in response.headers["Location"]
    assert response.headers["Location"].endswith("/nodes")


def test_form_post_can_redirect_back_to_node_list() -> None:
    client, execution_id, _, rerun_service = build_test_client()

    response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/rerun",
        data={
            "from_node_id": "step3",
            "next": f"/workflows/sample_workflow/executions/{execution_id}/nodes?status=failed",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes?status=failed"
    )
    assert rerun_service.calls[0]["from_node_id"] == "step3"


def test_api_workflows_returns_expected_schema() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get("/api/workflows")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == [
        {
            "workflow_id": "sample_workflow",
            "workflow_name": "Sample Workflow",
            "last_execution_id": execution_id,
            "last_status": "FAILED",
            "last_updated_at": None,
            "waiting_human_count": 1,
            "failed_count": 1,
        }
    ]


def test_api_node_cards_returns_expected_schema() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(f"/api/workflows/sample_workflow/executions/{execution_id}/nodes")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["node_id"] for item in payload] == ["step1", "step2", "step3"]
    assert payload[1]["status"] == "WAITING_HUMAN"


def test_unknown_workflow_returns_404() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(f"/workflows/unknown/executions/{execution_id}/nodes")

    assert response.status_code == 404


def test_unknown_execution_returns_404() -> None:
    client, _, _, _ = build_test_client()

    response = client.get("/workflows/sample_workflow/executions/unknown/nodes")

    assert response.status_code == 404


def test_unknown_node_returns_404() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.get(
        f"/workflows/sample_workflow/executions/{execution_id}/nodes/unknown"
    )

    assert response.status_code == 404


def test_missing_rerun_from_node_id_returns_400() -> None:
    client, execution_id, _, _ = build_test_client()

    response = client.post(
        f"/actions/workflows/sample_workflow/executions/{execution_id}/rerun",
        json={},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == 400
