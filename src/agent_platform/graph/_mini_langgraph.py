"""A tiny fallback runtime that mimics the subset of LangGraph used in Phase 1-6.

This is only used when the real `langgraph` package is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, TypeVar


START = "__START__"
END = "__END__"

StateT = TypeVar("StateT")


class StateGraph(Generic[StateT]):
    def __init__(self, state_schema: type[StateT]):
        self._state_schema = state_schema
        self._nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
        self._edges: dict[str, list[str]] = {}
        self._conditional_edges: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str] | None]] = {}

    def add_node(self, node_id: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._nodes[node_id] = fn

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._edges.setdefault(from_node, []).append(to_node)

    def add_conditional_edges(
        self,
        from_node: str,
        route_fn: Callable[[dict[str, Any]], str],
        path_map: dict[str, str] | None = None,
    ) -> None:
        self._conditional_edges[from_node] = (route_fn, dict(path_map) if isinstance(path_map, dict) else None)

    def compile(self) -> "CompiledGraph":
        return CompiledGraph(
            nodes=dict(self._nodes),
            edges={k: list(v) for k, v in self._edges.items()},
            conditional_edges=dict(self._conditional_edges),
        )


@dataclass
class CompiledGraph:
    nodes: Dict[str, Callable[[dict[str, Any]], dict[str, Any]]]
    edges: Dict[str, List[str]]
    conditional_edges: Dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str] | None]]

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current_state = dict(state)
        queue: list[str] = [START]
        visited_steps = 0
        max_steps = 10000

        while queue:
            current = queue.pop(0)

            conditional = self.conditional_edges.get(current)
            next_nodes: list[str]
            if conditional is not None:
                route_fn, path_map = conditional
                routed = route_fn(current_state)
                if path_map is not None:
                    target = path_map.get(str(routed))
                    next_nodes = [target] if isinstance(target, str) and target else []
                else:
                    next_nodes = [str(routed)] if routed else []
            else:
                next_nodes = self.edges.get(current, [])

            if not next_nodes:
                continue

            override_map = current_state.get("next_node_overrides")
            override_target = None
            if isinstance(override_map, dict):
                value = override_map.get(current)
                if isinstance(value, str) and value:
                    override_target = value

            if override_target is not None:
                if override_target not in next_nodes:
                    raise RuntimeError(
                        f"Invalid next node override from {current}: {override_target} not in {next_nodes}"
                    )
                selected_next_nodes = [override_target]
            elif len(next_nodes) == 1:
                selected_next_nodes = list(next_nodes)
            else:
                # 条件付きエッジ未定義の通常分岐は、全エッジを順次評価する。
                selected_next_nodes = list(next_nodes)

            for next_node in selected_next_nodes:
                if next_node == END:
                    continue

                if next_node not in self.nodes:
                    raise RuntimeError(f"Node not registered: {next_node}")

                delta = self.nodes[next_node](current_state)
                if delta:
                    for k, v in delta.items():
                        current_state[k] = v

                queue.append(next_node)
                visited_steps += 1
                if visited_steps > max_steps:
                    raise RuntimeError("Exceeded max steps in fallback graph runtime (possible cycle)")

        return current_state
