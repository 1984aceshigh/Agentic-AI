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

    for index, group_name in enumerate(sorted(grouped_nodes), start=1):
        group_id = f"group_{index}"
        group_label = escape_mermaid_label(group_name)
        lines.append(f'    subgraph {group_id}["{group_label}"]')
        for node in _sorted_nodes(grouped_nodes[group_name]):
            lines.append(f"        {build_mermaid_node_line(node)}")
        lines.append("    end")

    lines.append("")

    assessment_edge_labels = _collect_assessment_edge_labels(graph)
    for edge in _sorted_edges(graph.edges):
        label = assessment_edge_labels.get((edge.from_node, edge.to_node))
        lines.append(f"    {build_mermaid_edge_line(edge, label=label)}")

    return "\n".join(lines)


def build_mermaid_node_line(node: GraphNode) -> str:
    if not node.id or not node.id.strip():
        raise MermaidBuildError("node.id must not be empty")

    label = f"{escape_mermaid_label(node.name)}\\n({node.type.value})"
    return f'{node.id}["{label}"]'


def build_mermaid_edge_line(edge: GraphEdge, *, label: str | None = None) -> str:
    if not edge.from_node or not edge.from_node.strip():
        raise MermaidBuildError("edge.from_node must not be empty")
    if not edge.to_node or not edge.to_node.strip():
        raise MermaidBuildError("edge.to_node must not be empty")
    if label and label.strip():
        safe_label = _sanitize_mermaid_edge_label(label)
        return f"{edge.from_node} -->|{safe_label}| {edge.to_node}"
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


def _collect_assessment_edge_labels(graph: GraphModel) -> dict[tuple[str, str], str]:
    labels_map: dict[tuple[str, str], list[str]] = {}
    for node_id, node in graph.nodes.items():
        config = node.config if isinstance(node.config, dict) else {}
        task = str(config.get('task') or '').strip().lower()
        if task != 'assessment':
            continue
        routes = config.get('assessment_routes')
        if not isinstance(routes, dict):
            continue
        for option, target in routes.items():
            option_text = str(option).strip()
            if not option_text:
                continue
            if isinstance(target, list):
                targets = [str(item).strip() for item in target if str(item).strip()]
            else:
                target_text = str(target).strip()
                targets = [target_text] if target_text else []
            for to_node_id in targets:
                key = (node_id, to_node_id)
                labels_map.setdefault(key, [])
                if option_text not in labels_map[key]:
                    labels_map[key].append(option_text)
    return {key: ' / '.join(options) for key, options in labels_map.items() if options}


def _sanitize_mermaid_edge_label(label: str) -> str:
    text = str(label).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "／")
    text = text.replace('"', "'")
    text = text.replace("[", "［").replace("]", "］")
    return text.strip()
