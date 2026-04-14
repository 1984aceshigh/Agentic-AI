from __future__ import annotations

from collections import Counter
from typing import Any, Callable, TypeAlias

from typing_extensions import TypedDict

from agent_platform.models import GraphEdge, GraphModel, GraphNode

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore
except Exception:  # pragma: no cover
    from ._mini_langgraph import END, START, StateGraph


class Phase1LangGraphState(TypedDict, total=False):
    execution_id: str
    workflow_id: str
    node_states: dict[str, str]
    node_outputs: dict[str, dict[str, Any]]
    logs: list[str]


NodeFnFactory: TypeAlias = Callable[
    [GraphNode], Callable[[Phase1LangGraphState], Phase1LangGraphState]
]


class LangGraphCompileError(Exception):
    """Raised when GraphModel cannot be compiled into a Phase-1 minimal LangGraph."""


def _resolve_node_type_value(node: GraphNode) -> str:
    node_type = getattr(node, "type", None)
    if hasattr(node_type, "value"):
        return str(node_type.value)
    return str(node_type)


def make_dummy_node_fn(node: GraphNode) -> Callable[[Phase1LangGraphState], Phase1LangGraphState]:
    def _fn(state: Phase1LangGraphState) -> Phase1LangGraphState:
        old_states = dict(state.get("node_states") or {})
        old_outputs = dict(state.get("node_outputs") or {})
        old_logs = list(state.get("logs") or [])

        old_states[node.id] = "RUNNING"

        output = {
            "result": f"dummy output from {node.id}",
            "node_type": _resolve_node_type_value(node),
        }

        old_outputs[node.id] = output
        old_states[node.id] = "SUCCEEDED"

        updated: Phase1LangGraphState = {
            "node_states": old_states,
            "node_outputs": old_outputs,
            "logs": old_logs + [f"executed:{node.id}"],
        }

        # 実 LangGraph でも最終結果に残るよう、Phase 1 の固定キーを明示的に返す
        if "execution_id" in state:
            updated["execution_id"] = state["execution_id"]
        if "workflow_id" in state:
            updated["workflow_id"] = state["workflow_id"]

        return updated

    return _fn


def default_node_fn_factory(node: GraphNode) -> Callable[[Phase1LangGraphState], Phase1LangGraphState]:
    return make_dummy_node_fn(node)


def build_state_graph(
    graph: GraphModel,
    node_fn_factory: NodeFnFactory | None = None,
):
    factory = node_fn_factory or default_node_fn_factory

    _validate_graph_for_phase1(graph)

    builder = StateGraph(Phase1LangGraphState)

    for node in graph.nodes.values():
        builder.add_node(node.id, factory(node))

    builder.add_edge(START, graph.start_node)

    for edge in graph.edges:
        builder.add_edge(edge.from_node, edge.to_node)

    for end_node in graph.end_nodes:
        builder.add_edge(end_node, END)

    return builder


def compile_langgraph(graph: GraphModel, node_fn_factory: NodeFnFactory | None = None):
    try:
        return build_state_graph(graph, node_fn_factory=node_fn_factory).compile()
    except LangGraphCompileError:
        raise
    except Exception as exc:
        raise LangGraphCompileError(f"Failed to compile LangGraph: {exc}") from exc


def _validate_graph_for_phase1(graph: GraphModel) -> None:
    if not graph.start_node or not graph.start_node.strip():
        raise LangGraphCompileError("graph.start_node must not be empty")
    if not graph.nodes:
        raise LangGraphCompileError("graph.nodes must not be empty")
    if graph.start_node not in graph.nodes:
        raise LangGraphCompileError("graph.start_node must exist in graph.nodes")
    if not graph.end_nodes:
        raise LangGraphCompileError("graph.end_nodes must not be empty")

    for end_node in graph.end_nodes:
        if end_node not in graph.nodes:
            raise LangGraphCompileError(f"end_node does not exist in graph.nodes: {end_node}")

    node_ids = set(graph.nodes.keys())

    for edge in graph.edges:
        if edge.from_node not in node_ids:
            raise LangGraphCompileError(
                f"edge.from_node does not exist in graph.nodes: {edge.from_node}"
            )
        if edge.to_node not in node_ids:
            raise LangGraphCompileError(
                f"edge.to_node does not exist in graph.nodes: {edge.to_node}"
            )

    _check_branching_not_present(graph.edges)


def _check_branching_not_present(edges: list[GraphEdge]) -> None:
    counts = Counter(edge.from_node for edge in edges)
    for node_id, count in counts.items():
        if count >= 2:
            raise LangGraphCompileError(
                f"Branching is not supported in Phase 1 minimal compiler: node={node_id}"
            )