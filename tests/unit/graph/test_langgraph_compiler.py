from __future__ import annotations

from typing import Any, Callable

import pytest

from agent_platform.graph import LangGraphCompileError, compile_langgraph
from agent_platform.models import GraphEdge, GraphModel, GraphNode


def make_linear_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step2"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm", name="Step 1"),
            "step2": GraphNode(id="step2", type="llm", name="Step 2"),
        },
        edges=[GraphEdge(from_node="step1", to_node="step2")],
    )


def make_branching_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step3"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm", name="Step 1"),
            "step2": GraphNode(id="step2", type="llm", name="Step 2"),
            "step3": GraphNode(id="step3", type="human_gate", name="Step 3"),
        },
        edges=[
            GraphEdge(from_node="step1", to_node="step2"),
            GraphEdge(from_node="step1", to_node="step3"),
        ],
    )


def make_initial_state(graph: GraphModel) -> dict[str, Any]:
    return {
        "execution_id": "exec-1",
        "workflow_id": graph.workflow_id,
        "node_states": {},
        "node_outputs": {},
        "logs": [],
    }


def test_compile_langgraph_returns_compiled_graph() -> None:
    graph = make_linear_graph_model()

    compiled = compile_langgraph(graph)

    assert compiled is not None


def test_invoke_runs_two_node_linear_graph_end_to_end() -> None:
    graph = make_linear_graph_model()
    compiled = compile_langgraph(graph)

    result = compiled.invoke(make_initial_state(graph))

    assert result["workflow_id"] == "sample_workflow"
    assert result["node_states"] == {"step1": "SUCCEEDED", "step2": "SUCCEEDED"}
    assert set(result["node_outputs"].keys()) == {"step1", "step2"}
    assert result["node_outputs"]["step1"]["result"] == "dummy output from step1"
    assert result["node_outputs"]["step2"]["node_type"] == "llm"
    assert result["logs"] == ["executed:step1", "executed:step2"]


def test_custom_node_fn_factory_is_used() -> None:
    graph = make_linear_graph_model()

    def factory(node: GraphNode) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def _fn(state: dict[str, Any]) -> dict[str, Any]:
            states = dict(state.get("node_states") or {})
            outputs = dict(state.get("node_outputs") or {})
            logs = list(state.get("logs") or [])
            states[node.id] = "SUCCEEDED"
            outputs[node.id] = {"result": f"custom:{node.id}"}
            return {"node_states": states, "node_outputs": outputs, "logs": logs + [f"custom:{node.id}"]}

        return _fn

    compiled = compile_langgraph(graph, node_fn_factory=factory)

    result = compiled.invoke(make_initial_state(graph))

    assert result["node_outputs"]["step1"]["result"] == "custom:step1"
    assert result["logs"] == ["custom:step1", "custom:step2"]


def test_start_node_empty_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.start_node = ""

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)


def test_start_node_missing_in_nodes_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.start_node = "missing"

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)


def test_end_nodes_empty_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.end_nodes = []

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)


def test_edge_from_node_missing_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.edges = [GraphEdge(from_node="missing", to_node="step2")]

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)


def test_edge_to_node_missing_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.edges = [GraphEdge(from_node="step1", to_node="missing")]

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)


def test_branching_is_allowed_in_phase1_minimal_compiler() -> None:
    graph = make_branching_graph_model()

    compiled = compile_langgraph(graph)

    assert compiled is not None


def test_nodes_empty_raises() -> None:
    graph = make_linear_graph_model().model_copy(deep=True)
    graph.nodes = {}

    with pytest.raises(LangGraphCompileError):
        compile_langgraph(graph)
