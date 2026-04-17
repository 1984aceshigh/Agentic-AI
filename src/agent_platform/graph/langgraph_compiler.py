from __future__ import annotations

from typing import Annotated, Any, Callable, TypeAlias

from typing_extensions import TypedDict

from agent_platform.models import GraphEdge, GraphModel, GraphNode

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore
except Exception:  # pragma: no cover
    from ._mini_langgraph import END, START, StateGraph


def _merge_dicts(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(left or {})
    merged.update(right or {})
    return merged


def _concat_lists(left: list[str] | None, right: list[str] | None) -> list[str]:
    left_list = list(left or [])
    right_list = list(right or [])

    # 互換性維持: ノード関数が「差分」ではなく「全量スナップショット」
    # (old_logs + [new]) を返す実装でも重複しないようにする。
    if len(right_list) >= len(left_list) and right_list[: len(left_list)] == left_list:
        return right_list

    return left_list + right_list


def _or_bool(left: bool | None, right: bool | None) -> bool:
    return bool(left) or bool(right)


class Phase1LangGraphState(TypedDict, total=False):
    execution_id: str
    workflow_id: str
    node_states: Annotated[dict[str, str], _merge_dicts]
    node_outputs: Annotated[dict[str, dict[str, Any]], _merge_dicts]
    next_node_overrides: Annotated[dict[str, str], _merge_dicts]
    logs: Annotated[list[str], _concat_lists]
    halted: Annotated[bool, _or_bool]


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
        output = {
            "result": f"dummy output from {node.id}",
            "node_type": _resolve_node_type_value(node),
        }

        return {
            "node_states": {node.id: "SUCCEEDED"},
            "node_outputs": {node.id: output},
            "logs": [f"executed:{node.id}"],
        }

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

    outgoing_by_node: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing_by_node.setdefault(edge.from_node, []).append(edge.to_node)

    for from_node, to_nodes in outgoing_by_node.items():
        from_node_model = graph.nodes.get(from_node)
        from_config = getattr(from_node_model, "config", {}) if from_node_model is not None else {}
        is_assessment_router = (
            isinstance(from_config, dict)
            and str(from_config.get("task") or "").strip().lower() == "assessment"
            and isinstance(from_config.get("assessment_routes"), dict)
            and bool(from_config.get("assessment_routes"))
        )

        if len(to_nodes) <= 1 or not is_assessment_router:
            for to_node in to_nodes:
                builder.add_edge(from_node, to_node)
            continue

        path_map = {node_id: node_id for node_id in to_nodes}

        def _route(state: Phase1LangGraphState, *, _from_node: str = from_node, _to_nodes: list[str] = to_nodes) -> str:
            overrides = state.get("next_node_overrides")
            if isinstance(overrides, dict):
                override_target = overrides.get(_from_node)
                if isinstance(override_target, str) and override_target in _to_nodes:
                    return override_target
            return _to_nodes[0]

        if hasattr(builder, "add_conditional_edges"):
            builder.add_conditional_edges(from_node, _route, path_map)
        else:
            # Fallback safety: conditional API が無い実装では先頭エッジを採用。
            builder.add_edge(from_node, to_nodes[0])

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
