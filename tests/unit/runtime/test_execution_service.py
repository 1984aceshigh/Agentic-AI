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
                    "task": "assessment",
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


def test_execution_service_applies_assessment_next_node_override() -> None:
    graph = GraphModel(
        workflow_id="wf_branch",
        workflow_name="Workflow Branch",
        start_node="review",
        end_nodes=["publish", "rewrite"],
        nodes={
            "review": GraphNode(
                id="review",
                type="llm",
                name="Review",
                config={
                    "task": "assessment",
                    "prompt": "rework",
                    "assessment_options": ["pass", "rework"],
                    "assessment_routes": {"pass": "publish", "rework": "rewrite"},
                },
            ),
            "publish": GraphNode(id="publish", type="llm", name="Publish", config={"prompt": "publish"}),
            "rewrite": GraphNode(id="rewrite", type="llm", name="Rewrite", config={"prompt": "rewrite"}),
        },
        edges=[
            GraphEdge(from_node="review", to_node="publish"),
            GraphEdge(from_node="review", to_node="rewrite"),
        ],
    )
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

    context = context_manager.get_context(execution_id)
    assert context.node_states.get("review") == "SUCCEEDED"
    selected = context.node_outputs.get("review", {}).get("selected_option")
    next_node = context.node_outputs.get("review", {}).get("next_node")
    assert selected in {"pass", "rework"}
    assert next_node in {"publish", "rewrite"}
    if selected == "pass":
        assert context.node_states.get("publish") == "SUCCEEDED"
        assert context.node_states.get("rewrite") is None
    else:
        assert selected == "rework"
        assert context.node_states.get("rewrite") == "SUCCEEDED"
        assert context.node_states.get("publish") is None


def test_execution_service_assessment_true_false_routes_execute_only_selected_branch() -> None:
    graph = GraphModel(
        workflow_id="wf_bool_branch",
        workflow_name="Workflow Bool Branch",
        start_node="judge",
        end_nodes=["node_true", "node_false"],
        nodes={
            "judge": GraphNode(
                id="judge",
                type="llm",
                name="Judge",
                config={
                    "task": "assessment",
                    "prompt": "false",
                    "assessment_options": ["true", "false"],
                    "assessment_routes": {"true": "node_true", "false": "node_false"},
                },
            ),
            "node_true": GraphNode(id="node_true", type="llm", name="True Node", config={"prompt": "true"}),
            "node_false": GraphNode(id="node_false", type="llm", name="False Node", config={"prompt": "false"}),
        },
        edges=[
            GraphEdge(from_node="judge", to_node="node_true"),
            GraphEdge(from_node="judge", to_node="node_false"),
        ],
    )
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

    context = context_manager.get_context(execution_id)
    assert context.node_states.get("judge") == "SUCCEEDED"
    assert context.node_outputs.get("judge", {}).get("selected_option") == "false"
    assert context.node_outputs.get("judge", {}).get("next_node") == "node_false"
    assert context.node_states.get("node_false") == "SUCCEEDED"
    assert context.node_states.get("node_true") is None


def test_execution_service_non_assessment_branch_executes_all_outgoing_nodes() -> None:
    graph = GraphModel(
        workflow_id="wf_parallel_branch",
        workflow_name="Workflow Parallel Branch",
        start_node="start",
        end_nodes=["first_node", "node_04", "second_node"],
        nodes={
            "start": GraphNode(id="start", type="llm", name="Start", config={"task": "generate", "prompt": "start"}),
            "first_node": GraphNode(id="first_node", type="llm", name="First", config={"prompt": "first"}),
            "node_04": GraphNode(id="node_04", type="llm", name="Node 04", config={"prompt": "node_04"}),
            "second_node": GraphNode(id="second_node", type="llm", name="Second", config={"prompt": "second"}),
        },
        edges=[
            GraphEdge(from_node="start", to_node="first_node"),
            GraphEdge(from_node="start", to_node="node_04"),
            GraphEdge(from_node="start", to_node="second_node"),
        ],
    )
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
    context = context_manager.get_context(execution_id)

    assert context.node_states.get("start") == "SUCCEEDED"
    assert context.node_states.get("first_node") == "SUCCEEDED"
    assert context.node_states.get("node_04") == "SUCCEEDED"
    assert context.node_states.get("second_node") == "SUCCEEDED"


def test_execution_service_marks_failed_when_llm_executor_errors() -> None:
    graph = GraphModel(
        workflow_id="wf_fail",
        workflow_name="Workflow Failure",
        start_node="bad_llm",
        end_nodes=["bad_llm"],
        nodes={
            "bad_llm": GraphNode(
                id="bad_llm",
                type="llm",
                name="Bad LLM",
                config={
                    "task": "generate",
                    "prompt": "hello",
                    "temperature": "not-a-number",
                },
            ),
        },
        edges=[],
    )
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

    context = context_manager.get_context(execution_id)
    assert context.node_states.get("bad_llm") == "FAILED"
    workflow_record = records_manager.get_workflow_record(execution_id)
    assert workflow_record.status == "FAILED"
    node_record = records_manager.get_node_record(execution_id, "bad_llm")
    assert node_record.status == "FAILED"
    assert node_record.error_message is not None
