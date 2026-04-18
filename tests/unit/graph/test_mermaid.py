from __future__ import annotations

import pytest

from agent_platform.graph import (
    MermaidBuildError,
    build_mermaid,
    build_mermaid_edge_line,
    build_mermaid_node_line,
    escape_mermaid_label,
)
from agent_platform.models import GraphEdge, GraphModel, GraphNode


def make_graph_node(
    node_id: str,
    *,
    node_type: str = "llm",
    name: str = "Step",
    group: str | None = None,
) -> GraphNode:
    return GraphNode(id=node_id, type=node_type, name=name, group=group)



def make_graph_model(*, direction: str = "TD") -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step2"],
        direction=direction,
        nodes={
            "step1": make_graph_node("step1", name="Step 1"),
            "step2": make_graph_node("step2", node_type="human_gate", name="Step 2"),
        },
        edges=[GraphEdge(from_node="step1", to_node="step2")],
    )



def test_build_mermaid_from_minimal_graph_model() -> None:
    graph = make_graph_model()

    mermaid = build_mermaid(graph)

    assert isinstance(mermaid, str)
    assert 'step1["Step 1\\n(llm)"]' in mermaid
    assert "step1 --> step2" in mermaid



def test_first_line_is_flowchart_td() -> None:
    mermaid = build_mermaid(make_graph_model())

    assert mermaid.splitlines()[0] == "flowchart TD"



def test_direction_lr_is_reflected() -> None:
    mermaid = build_mermaid(make_graph_model(direction="LR"))

    assert mermaid.splitlines()[0] == "flowchart LR"



def test_build_mermaid_node_line_returns_expected_format() -> None:
    node = make_graph_node("step1", name="Task Understanding")

    line = build_mermaid_node_line(node)

    assert line == 'step1["Task Understanding\\n(llm)"]'



def test_build_mermaid_edge_line_returns_expected_format() -> None:
    edge = GraphEdge(from_node="step1", to_node="step2")

    line = build_mermaid_edge_line(edge)

    assert line == "step1 --> step2"


def test_build_mermaid_edge_line_with_label_returns_expected_format() -> None:
    edge = GraphEdge(from_node="step1", to_node="step2")

    line = build_mermaid_edge_line(edge, label="pass")

    assert line == 'step1 -->|pass| step2'



def test_group_less_nodes_are_rendered_at_top_level() -> None:
    mermaid = build_mermaid(make_graph_model())

    assert "    step1[\"Step 1\\n(llm)\"]" in mermaid
    assert "subgraph" not in mermaid



def test_nodes_in_same_group_are_wrapped_in_subgraph() -> None:
    graph = make_graph_model()
    graph.nodes = {
        "step1": make_graph_node("step1", name="Step 1", group="review"),
        "step2": make_graph_node("step2", node_type="human_gate", name="Step 2", group="review"),
    }

    mermaid = build_mermaid(graph)

    assert '    subgraph group_1["review"]' in mermaid
    assert "        step1[\"Step 1\\n(llm)\"]" in mermaid
    assert "        step2[\"Step 2\\n(human_gate)\"]" in mermaid
    assert "    end" in mermaid



def test_grouped_and_ungrouped_nodes_can_coexist() -> None:
    graph = make_graph_model()
    graph.nodes["step3"] = make_graph_node("step3", name="Step 3", group="review")
    graph.edges.append(GraphEdge(from_node="step2", to_node="step3"))

    mermaid = build_mermaid(graph)

    assert "    step1[\"Step 1\\n(llm)\"]" in mermaid
    assert "    step2[\"Step 2\\n(human_gate)\"]" in mermaid
    assert '    subgraph group_1["review"]' in mermaid
    assert "        step3[\"Step 3\\n(llm)\"]" in mermaid



def test_node_output_order_is_deterministic() -> None:
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="b",
        end_nodes=["c"],
        direction="TD",
        nodes={
            "c": make_graph_node("c", name="C"),
            "a": make_graph_node("a", name="A"),
            "b": make_graph_node("b", name="B", group="g1"),
        },
        edges=[GraphEdge(from_node="b", to_node="c")],
    )

    mermaid = build_mermaid(graph)
    lines = mermaid.splitlines()

    assert lines[1] == '    a["A\\n(llm)"]'
    assert lines[2] == '    c["C\\n(llm)"]'
    assert lines[3] == '    subgraph group_1["g1"]'
    assert lines[4] == '        b["B\\n(llm)"]'



def test_edge_output_order_is_deterministic() -> None:
    graph = make_graph_model()
    graph.edges = [
        GraphEdge(from_node="step2", to_node="step3"),
        GraphEdge(from_node="step1", to_node="step2"),
        GraphEdge(from_node="step1", to_node="step1"),
    ]

    mermaid = build_mermaid(graph)
    edge_lines = [line for line in mermaid.splitlines() if "-->" in line]

    assert edge_lines == [
        "    step1 --> step1",
        "    step1 --> step2",
        "    step2 --> step3",
    ]


def test_assessment_routes_are_rendered_as_edge_labels() -> None:
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="judge",
        end_nodes=["publish", "rewrite"],
        direction="TD",
        nodes={
            "judge": GraphNode(
                id="judge",
                type="llm",
                name="Judge",
                config={
                    "task": "assessment",
                    "assessment_routes": {"pass": "publish", "rework": "rewrite"},
                },
            ),
            "publish": GraphNode(id="publish", type="llm", name="Publish"),
            "rewrite": GraphNode(id="rewrite", type="llm", name="Rewrite"),
        },
        edges=[
            GraphEdge(from_node="judge", to_node="publish"),
            GraphEdge(from_node="judge", to_node="rewrite"),
        ],
    )

    mermaid = build_mermaid(graph)

    assert 'judge -->|pass| publish' in mermaid
    assert 'judge -->|rework| rewrite' in mermaid



def test_escape_mermaid_label_escapes_double_quote() -> None:
    escaped = escape_mermaid_label('Say "hello"')

    assert escaped == 'Say \\"hello\\"'



def test_escape_mermaid_label_replaces_square_brackets() -> None:
    escaped = escape_mermaid_label("Task [A]")

    assert escaped == "Task ［A］"



def test_escape_mermaid_label_normalizes_newlines() -> None:
    escaped = escape_mermaid_label("Line1\r\nLine2")

    assert escaped == "Line1\\nLine2"



def test_build_mermaid_raises_when_workflow_id_is_empty() -> None:
    graph = make_graph_model().model_copy(deep=True)
    graph.workflow_id = ""

    with pytest.raises(MermaidBuildError, match="workflow_id"):
        build_mermaid(graph)



def test_build_mermaid_raises_when_direction_is_empty() -> None:
    graph = make_graph_model().model_copy(deep=True)
    graph.direction = ""

    with pytest.raises(MermaidBuildError, match="direction"):
        build_mermaid(graph)



def test_build_mermaid_node_line_raises_when_node_id_is_empty() -> None:
    node = GraphNode.model_construct(id="", type="llm", name="Broken")

    with pytest.raises(MermaidBuildError, match="node.id"):
        build_mermaid_node_line(node)
