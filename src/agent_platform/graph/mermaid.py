from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from agent_platform.models import GraphEdge, GraphModel, GraphNode


class MermaidBuildError(Exception):
    """Raised when a GraphModel cannot be converted into Mermaid text."""


def build_mermaid(graph: GraphModel) -> str:
    if not graph.workflow_id or not graph.workflow_id.strip():
        raise MermaidBuildError("graph.workflow_id must not be empty")
    if not graph.direction or not graph.direction.strip():
        raise MermaidBuildError("graph.direction must not be empty")

    lines: list[str] = [f"flowchart {graph.direction}"]

    ungrouped_nodes, grouped_nodes = _group_nodes_by_group(graph.nodes.values())

    for node in _sorted_nodes(ungrouped_nodes):
        lines.append(f"    {build_mermaid_node_line(node)}")

    for group_name in sorted(grouped_nodes):
        lines.append(f"    subgraph {group_name}")
        for node in _sorted_nodes(grouped_nodes[group_name]):
            lines.append(f"        {build_mermaid_node_line(node)}")
        lines.append("    end")

    lines.append("")

    for edge in _sorted_edges(graph.edges):
        lines.append(f"    {build_mermaid_edge_line(edge)}")

    return "\n".join(lines)


def build_mermaid_node_line(node: GraphNode) -> str:
    if not node.id or not node.id.strip():
        raise MermaidBuildError("node.id must not be empty")

    label = f"{escape_mermaid_label(node.name)}\\n({node.type.value})"
    return f'{node.id}["{label}"]'


def build_mermaid_edge_line(edge: GraphEdge) -> str:
    if not edge.from_node or not edge.from_node.strip():
        raise MermaidBuildError("edge.from_node must not be empty")
    if not edge.to_node or not edge.to_node.strip():
        raise MermaidBuildError("edge.to_node must not be empty")
    return f"{edge.from_node} --> {edge.to_node}"


def escape_mermaid_label(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = normalized.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("[", "［").replace("]", "］")
    escaped = escaped.replace("\n", "\\n")
    return escaped


def _group_nodes_by_group(nodes: Iterable[GraphNode]) -> tuple[list[GraphNode], dict[str, list[GraphNode]]]:
    ungrouped: list[GraphNode] = []
    grouped: dict[str, list[GraphNode]] = defaultdict(list)

    for node in nodes:
        if node.group is None or node.group == "":
            ungrouped.append(node)
        else:
            grouped[node.group].append(node)

    return ungrouped, dict(grouped)


def _sorted_nodes(nodes: Iterable[GraphNode]) -> list[GraphNode]:
    return sorted(nodes, key=lambda node: node.id)


def _sorted_edges(edges: Iterable[GraphEdge]) -> list[GraphEdge]:
    return sorted(edges, key=lambda edge: (edge.from_node, edge.to_node))
