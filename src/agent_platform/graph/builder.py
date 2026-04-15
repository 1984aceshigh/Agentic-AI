from __future__ import annotations

from typing import Any

from agent_platform.models import EdgeSpec, GraphEdge, GraphModel, GraphNode, NodeSpec, WorkflowSpec


class GraphBuildError(Exception):
    """Raised when a WorkflowSpec cannot be converted into a GraphModel."""


def build_graph_model(spec: WorkflowSpec) -> GraphModel:
    if not spec.workflow.id:
        raise GraphBuildError("workflow.id must not be empty")
    if not spec.runtime.start_node:
        raise GraphBuildError("runtime.start_node must not be empty")

    direction = "TD"
    if spec.display is not None and spec.display.mermaid is not None:
        direction = spec.display.mermaid.direction

    graph_nodes: dict[str, GraphNode] = {}
    for node in spec.nodes:
        graph_node = build_graph_node(node)
        if graph_node.id in graph_nodes:
            raise GraphBuildError(f"duplicate node id during graph build: {graph_node.id}")
        graph_nodes[graph_node.id] = graph_node

    graph_edges = [build_graph_edge(edge) for edge in spec.edges]

    return GraphModel(
        workflow_id=spec.workflow.id,
        workflow_name=spec.workflow.name,
        start_node=spec.runtime.start_node,
        end_nodes=list(spec.runtime.end_nodes),
        nodes=graph_nodes,
        edges=graph_edges,
        direction=direction,
    )


def build_graph_node(node: NodeSpec) -> GraphNode:
    return GraphNode(
        id=node.id,
        type=node.type,
        name=node.name,
        description=node.description,
        config=dict(node.config),
        input=node.input.model_dump(by_alias=True) if node.input is not None else {},
        group=node.display.group if node.display is not None else None,
    )


def build_graph_edge(edge: EdgeSpec) -> GraphEdge:
    if not edge.from_node:
        raise GraphBuildError("edge.from_node must not be empty")
    if not edge.to_node:
        raise GraphBuildError("edge.to_node must not be empty")

    return GraphEdge(from_node=edge.from_node, to_node=edge.to_node)


def dump_graph_model(graph: GraphModel) -> dict[str, Any]:
    return {
        "workflow_id": graph.workflow_id,
        "workflow_name": graph.workflow_name,
        "start_node": graph.start_node,
        "end_nodes": list(graph.end_nodes),
        "direction": graph.direction,
        "nodes": {
            node_id: {
                "id": node.id,
                "type": node.type.value,
                "name": node.name,
                "description": node.description,
                "group": node.group,
                "config": dict(node.config),
                "input": dict(node.input),
            }
            for node_id, node in graph.nodes.items()
        },
        "edges": [
            {"from_node": edge.from_node, "to_node": edge.to_node}
            for edge in graph.edges
        ],
    }
