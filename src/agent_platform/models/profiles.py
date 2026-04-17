from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ContractType(str, Enum):
    LLM_COMPLETION = "llm_completion"
    MEMORY_STORE = "memory_store"
    VECTOR_RETRIEVER = "vector_retriever"
    TOOL_INVOCATION = "tool_invocation"
    FILE_ACCESS = "file_access"


class NodeType(str, Enum):
    LLM = "llm"
    HUMAN_GATE = "human_gate"
    API = "api"
    MCP = "mcp"

    @classmethod
    def _missing_(cls, value: object) -> "NodeType" | None:
        legacy = {
            "llm_generate": cls.LLM,
            "llm_review": cls.LLM,
            "memory_read": cls.LLM,
            "memory_write": cls.LLM,
            "rag_retrieve": cls.LLM,
            "deterministic_transform": cls.LLM,
            "tool_invoke": cls.API,
            "file_read": cls.API,
            "file_write": cls.API,
        }
        if isinstance(value, str):
            return legacy.get(value.strip().lower())
        return None


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING_HUMAN = "WAITING_HUMAN"
    SKIPPED = "SKIPPED"


class LLMProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    adapter_ref: str | None = None
    connection_ref: str | None = None
    contract: ContractType | None = None
    capabilities: list[str] = Field(default_factory=list)
    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None


class MemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    adapter_ref: str | None = None
    connection_ref: str | None = None
    contract: ContractType | None = None
    capabilities: list[str] = Field(default_factory=list)
    backend: str
    namespace: str | None = None


class RAGProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    adapter_ref: str | None = None
    connection_ref: str | None = None
    contract: ContractType | None = None
    capabilities: list[str] = Field(default_factory=list)
    backend: str
    collection: str
    embedding_model: str
    top_k: int | None = 5


class ToolProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    adapter_ref: str | None = None
    connection_ref: str | None = None
    contract: ContractType | None = None
    capabilities: list[str] = Field(default_factory=list)
    server_name: str | None = None
    root_alias: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
