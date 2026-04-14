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
    LLM_GENERATE = "llm_generate"
    LLM_REVIEW = "llm_review"
    DETERMINISTIC_TRANSFORM = "deterministic_transform"
    HUMAN_GATE = "human_gate"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    RAG_RETRIEVE = "rag_retrieve"
    TOOL_INVOKE = "tool_invoke"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"


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
