from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .profiles import NodeType


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    type: NodeType
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    group: str | None = None


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str
    to_node: str


class GraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workflow_id: str
    workflow_name: str
    start_node: str
    end_nodes: list[str]
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: list[GraphEdge] = Field(default_factory=list)
    direction: str = "TD"
