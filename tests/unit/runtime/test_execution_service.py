from __future__ import annotations

from agent_platform.models import GraphEdge, GraphModel, GraphNode
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.execution_service import WorkflowExecutionService
from agent_platform.runtime.records_manager import ExecutionRecordsManager


def _build_graph() -> GraphModel:
    return GraphModel(
        workflow_id="wf_exec",
        workflow_name="Workflow Execution",
        start_node="generate",
        end_nodes=["review"],
        nodes={
            "generate": GraphNode(
                id="generate",
                type="llm",
                name="Generate",
                config={
                    "prompt": "Write report",
                    "task": "generate",
                    "input_definition": "topic: string",
                    "output_format": "text",
                },
            ),
            "review": GraphNode(
                id="review",
                type="llm",
                name="Review",
                config={
                    "prompt": "Review draft",
                    "task": "review",
                    "input_definition": "ref: generate.result",
                    "output_format": "text",
                },
                input={"from": [{"node": "generate", "key": "result"}]},
            ),
        },
        edges=[GraphEdge(from_node="generate", to_node="review")],
    )


def test_execution_service_run_workflow_updates_runtime_state() -> None:
    graph = _build_graph()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    latest_execution_ids: dict[str, str | None] = {}
    service = WorkflowExecutionService(
        context_manager=context_manager,
        records_manager=records_manager,
        workflow_graphs={graph.workflow_id: graph},
        latest_execution_ids=latest_execution_ids,
    )

    execution_id = service.run_workflow(graph.workflow_id)

    assert latest_execution_ids[graph.workflow_id] == execution_id

    context = context_manager.get_context(execution_id)
    assert context.node_states["generate"] == "SUCCEEDED"
    assert context.node_states["review"] == "SUCCEEDED"
    assert isinstance(context.node_outputs["generate"]["result"], str)
    assert "Write report" in context.node_outputs["generate"]["result"]
    assert "Input definition:\ntopic: string" in context.node_outputs["generate"]["result"]
    assert "Review draft" in context.node_outputs["review"]["review"]
    assert "Write report" in context.node_outputs["review"]["review"]
    assert "Resolved inputs:" in context.node_outputs["review"]["review"]

    workflow_record = records_manager.get_workflow_record(execution_id)
    assert workflow_record.status == "SUCCEEDED"
    generate_record = records_manager.get_node_record(execution_id, "generate")
    review_record = records_manager.get_node_record(execution_id, "review")
    assert isinstance(generate_record.input_preview, str)
    assert "Write report" in generate_record.input_preview
    assert "Input definition:\ntopic: string" in generate_record.input_preview
    assert isinstance(review_record.input_preview, str)
    assert "Review draft" in review_record.input_preview
    assert isinstance(generate_record.output_preview, str)
    assert "Write report" in generate_record.output_preview
    assert isinstance(review_record.output_preview, str)
    assert "Review draft" in review_record.output_preview


def test_execution_service_rerun_from_node_marks_running() -> None:
    graph = _build_graph()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    latest_execution_ids: dict[str, str | None] = {}
    service = WorkflowExecutionService(
        context_manager=context_manager,
        records_manager=records_manager,
        workflow_graphs={graph.workflow_id: graph},
        latest_execution_ids=latest_execution_ids,
    )

    execution_id = service.run_workflow(graph.workflow_id)
    service.rerun_from_node(
        workflow_id=graph.workflow_id,
        execution_id=execution_id,
        from_node_id="review",
    )

    context = context_manager.get_context(execution_id)
    assert context.node_states["review"] == "RUNNING"
    record = records_manager.get_node_record(execution_id, "review")
    assert record.status == "RUNNING"
