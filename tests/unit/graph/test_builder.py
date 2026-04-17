from __future__ import annotations

import pytest

from agent_platform.graph import GraphBuildError, build_graph_edge, build_graph_model, build_graph_node, dump_graph_model
from agent_platform.models import (
    DisplaySpec,
    EdgeSpec,
    GraphEdge,
    GraphModel,
    GraphNode,
    IntegrationProfiles,
    MermaidDisplaySpec,
    NodeDisplaySpec,
    NodeSpec,
    WorkflowMeta,
    WorkflowSpec,
)


def make_valid_workflow_spec() -> WorkflowSpec:
    return WorkflowSpec(
        schema_version="0.1",
        workflow=WorkflowMeta(id="sample_workflow", name="Sample Workflow"),
        runtime={"start_node": "step1", "end_nodes": ["step2"]},
        integrations=IntegrationProfiles(),
        nodes=[
            NodeSpec(
                id="step1",
                type="llm_generate",
                name="Step 1",
                config={"llm_profile": "default_llm", "prompt": "hello"},
            ),
            NodeSpec(
                id="step2",
                type="human_gate",
                name="Step 2",
                display=NodeDisplaySpec(group="review"),
            ),
        ],
        edges=[EdgeSpec(**{"from": "step1", "to": "step2"})],
        display=DisplaySpec(mermaid=MermaidDisplaySpec(direction="LR")),
    )


def test_build_graph_model_from_valid_workflow_spec() -> None:
    spec = make_valid_workflow_spec()

    graph = build_graph_model(spec)

    assert isinstance(graph, GraphModel)
    assert graph.workflow_id == "sample_workflow"
    assert graph.workflow_name == "Sample Workflow"
    assert graph.start_node == "step1"
    assert graph.end_nodes == ["step2"]


def test_nodes_are_stored_as_dict_of_graph_nodes() -> None:
    spec = make_valid_workflow_spec()

    graph = build_graph_model(spec)

    assert isinstance(graph.nodes, dict)
    assert set(graph.nodes.keys()) == {"step1", "step2"}
    assert isinstance(graph.nodes["step1"], GraphNode)
    assert graph.nodes["step2"].group == "review"


def test_edges_are_stored_as_graph_edge_list() -> None:
    spec = make_valid_workflow_spec()

    graph = build_graph_model(spec)

    assert isinstance(graph.edges, list)
    assert graph.edges == [GraphEdge(from_node="step1", to_node="step2")]


def test_display_direction_is_reflected() -> None:
    spec = make_valid_workflow_spec()

    graph = build_graph_model(spec)

    assert graph.direction == "LR"


def test_direction_defaults_to_td_when_display_is_missing() -> None:
    spec = make_valid_workflow_spec().model_copy(deep=True)
    spec.display = None

    graph = build_graph_model(spec)

    assert graph.direction == "TD"


def test_build_graph_node_reflects_group_and_copies_config() -> None:
    node = NodeSpec(
        id="step1",
        type="llm_generate",
        name="Step 1",
        config={"llm_profile": "default_llm", "temperature": 0.2},
        display=NodeDisplaySpec(group="analysis"),
    )

    graph_node = build_graph_node(node)

    assert graph_node == GraphNode(
        id="step1",
        type="llm",
        name="Step 1",
        description=None,
        config={"llm_profile": "default_llm", "temperature": 0.2},
        input={},
        group="analysis",
    )
    assert graph_node.config is not node.config


def test_build_graph_edge_converts_edge_spec() -> None:
    edge = EdgeSpec(**{"from": "step1", "to": "step2"})

    graph_edge = build_graph_edge(edge)

    assert graph_edge == GraphEdge(from_node="step1", to_node="step2")


def test_dump_graph_model_returns_json_friendly_dict() -> None:
    spec = make_valid_workflow_spec()
    graph = build_graph_model(spec)

    dumped = dump_graph_model(graph)

    assert dumped == {
        "workflow_id": "sample_workflow",
        "workflow_name": "Sample Workflow",
        "start_node": "step1",
        "end_nodes": ["step2"],
        "direction": "LR",
        "nodes": {
            "step1": {
                "id": "step1",
                    "type": "llm",
                "name": "Step 1",
                "description": None,
                "group": None,
                "config": {"llm_profile": "default_llm", "prompt": "hello"},
                "input": {},
            },
            "step2": {
                "id": "step2",
                "type": "human_gate",
                "name": "Step 2",
                "description": None,
                "group": "review",
                "config": {},
                "input": {},
            },
        },
        "edges": [{"from_node": "step1", "to_node": "step2"}],
    }


def test_build_graph_model_raises_when_workflow_id_is_empty() -> None:
    spec = make_valid_workflow_spec().model_copy(deep=True)
    spec.workflow.id = ""

    with pytest.raises(GraphBuildError, match="workflow.id"):
        build_graph_model(spec)


def test_build_graph_model_raises_when_start_node_is_empty() -> None:
    spec = make_valid_workflow_spec().model_copy(deep=True)
    spec.runtime.start_node = ""

    with pytest.raises(GraphBuildError, match="start_node"):
        build_graph_model(spec)


def test_build_graph_model_raises_on_duplicate_node_ids() -> None:
    spec = make_valid_workflow_spec().model_copy(deep=True)
    spec.nodes.append(
        NodeSpec(
            id="step1",
            type="human_gate",
            name="Another Step 1",
        )
    )

    with pytest.raises(GraphBuildError, match="duplicate node id"):
        build_graph_model(spec)


@pytest.mark.parametrize(
    ("edge_kwargs", "expected_message"),
    [
        ({"from": "", "to": "step2"}, "from_node"),
        ({"from": "step1", "to": ""}, "to_node"),
    ],
)
def test_build_graph_edge_raises_for_empty_endpoints(edge_kwargs: dict[str, str], expected_message: str) -> None:
    edge = EdgeSpec.model_construct(from_node=edge_kwargs["from"], to_node=edge_kwargs["to"])

    with pytest.raises(GraphBuildError, match=expected_message):
        build_graph_edge(edge)
