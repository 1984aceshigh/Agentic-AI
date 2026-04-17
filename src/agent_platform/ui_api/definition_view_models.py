from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _BaseViewModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WorkflowDefinitionSummaryView(_BaseViewModel):
    workflow_id: str
    workflow_name: str
    version: str | None = None
    updated_at: str | None = None
    is_archived: bool = False
    validation_status: str | None = None
    node_count: int | None = None
    edge_count: int | None = None


class NodeSummaryView(_BaseViewModel):
    node_id: str
    node_name: str
    node_type: str
    group: str | None = None
    selected: bool = False


class EdgeSummaryView(_BaseViewModel):
    from_node_id: str
    to_node_id: str
    label: str | None = None


class InputDefinitionCandidateView(_BaseViewModel):
    node_id: str
    node_name: str
    output_key: str
    ref_expression: str


class EdgeConnectionNodeView(_BaseViewModel):
    node_id: str
    node_name: str
    node_type: str


class RAGDatasetOptionView(_BaseViewModel):
    dataset_id: str
    name: str
    source_filename: str
    source_type: str
    chunk_count: int


class NodeEditorView(_BaseViewModel):
    node_id: str = ''
    node_name: str = ''
    node_type: str = ''
    group: str | None = None
    is_llm_node: bool = False
    llm_task: str = 'generate'
    llm_temperature: str = ''
    llm_prompt: str = ''
    llm_input_definition: str = ''
    llm_output_format: str = ''
    llm_assessment_options: str = ''
    llm_assessment_routes: str = ''
    llm_extract_fields: str = ''
    llm_extract_output_format: str = 'json'
    input_definition_candidates: list[InputDefinitionCandidateView] = Field(default_factory=list)
    edge_connection_candidates: list[EdgeConnectionNodeView] = Field(default_factory=list)
    selected_outgoing_connections: list[EdgeConnectionNodeView] = Field(default_factory=list)
    rag_dataset_options: list[RAGDatasetOptionView] = Field(default_factory=list)
    selected_rag_dataset_id: str | None = None
    advanced_yaml_fragment: str = ''
    incoming_edges: list[EdgeSummaryView] = Field(default_factory=list)
    outgoing_edges: list[EdgeSummaryView] = Field(default_factory=list)
    deletable: bool = True


class EdgeEditorView(_BaseViewModel):
    from_node_id: str = ''
    to_node_id: str = ''
    label: str | None = None
    advanced_yaml_fragment: str = ''


class GraphEditorView(_BaseViewModel):
    workflow_id: str
    workflow_name: str
    version: str | None = None
    description: str | None = None
    is_archived: bool = False
    selected_node_id: str | None = None
    selected_tab: str = 'nodes'
    yaml_text: str
    mermaid_text: str = 'graph TD\n'
    node_summaries: list[NodeSummaryView] = Field(default_factory=list)
    edge_summaries: list[EdgeSummaryView] = Field(default_factory=list)
    rag_dataset_options: list[RAGDatasetOptionView] = Field(default_factory=list)
    selected_node_editor: NodeEditorView | None = None
    edge_editor: EdgeEditorView = Field(default_factory=EdgeEditorView)
    validation_status: str = 'valid'
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    is_dirty: bool = False

