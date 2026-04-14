from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .profiles import LLMProfile, MemoryProfile, NodeType, RAGProfile, ToolProfile


class WorkflowMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class RuntimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start_node: str
    end_nodes: list[str]


class MermaidDisplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    direction: str = "TD"


class DisplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mermaid: MermaidDisplaySpec | None = None


class IntegrationProfiles(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    llm_profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    memory_profiles: dict[str, MemoryProfile] = Field(default_factory=dict)
    rag_profiles: dict[str, RAGProfile] = Field(default_factory=dict)
    tool_profiles: dict[str, ToolProfile] = Field(default_factory=dict)


class NodeInputSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    node: str
    key: str


class NodeInputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: list[NodeInputSource] = Field(default_factory=list, alias="from")


class NodeOutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str | None = None


class RetrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    max_attempts: int = 1


class NodeDisplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    group: str | None = None


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    type: NodeType
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    input: NodeInputSpec | None = None
    output: NodeOutputSpec | None = None
    retry: RetrySpec | None = None
    display: NodeDisplaySpec | None = None


class EdgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str
    workflow: WorkflowMeta
    runtime: RuntimeSpec
    integrations: IntegrationProfiles
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    display: DisplaySpec | None = None

    @model_validator(mode="after")
    def validate_minimum_structure(self) -> "WorkflowSpec":
        if not self.schema_version.strip():
            raise ValueError("schema_version must not be empty")
        if not self.nodes:
            raise ValueError("nodes must not be empty")
        if not self.runtime.end_nodes:
            raise ValueError("runtime.end_nodes must not be empty")
        return self
