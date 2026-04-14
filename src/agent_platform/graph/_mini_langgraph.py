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

    def add_node(self, node_id: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._nodes[node_id] = fn

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._edges.setdefault(from_node, []).append(to_node)

    def compile(self) -> "CompiledGraph":
        return CompiledGraph(nodes=dict(self._nodes), edges={k: list(v) for k, v in self._edges.items()})


@dataclass
class CompiledGraph:
    nodes: Dict[str, Callable[[dict[str, Any]], dict[str, Any]]]
    edges: Dict[str, List[str]]

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current = START
        current_state = dict(state)

        while True:
            next_nodes = self.edges.get(current, [])
            if not next_nodes:
                # no outgoing edge => stop
                return current_state
            if len(next_nodes) != 1:
                raise RuntimeError(f"Ambiguous next node(s) from {current}: {next_nodes}")

            next_node = next_nodes[0]
            if next_node == END:
                return current_state

            if next_node not in self.nodes:
                raise RuntimeError(f"Node not registered: {next_node}")

            delta = self.nodes[next_node](current_state)
            if delta:
                for k, v in delta.items():
                    current_state[k] = v

            current = next_node
