from __future__ import annotations

from agent_platform.models import GraphModel


def test_graph_model_can_be_created() -> None:
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="start",
        end_nodes=["end"],
    )
    assert graph.workflow_id == "sample_workflow"
    assert graph.direction == "TD"


def test_graph_model_keeps_nodes_as_dict() -> None:
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="start",
        end_nodes=["end"],
        nodes={
            "start": {"id": "start", "type": "llm_generate", "name": "Start"},
            "end": {"id": "end", "type": "llm_review", "name": "End"},
        },
    )
    assert isinstance(graph.nodes, dict)
    assert set(graph.nodes.keys()) == {"start", "end"}
