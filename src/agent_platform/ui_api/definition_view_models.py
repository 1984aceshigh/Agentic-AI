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


class NodeEditorView(_BaseViewModel):
    node_id: str = ''
    node_name: str = ''
    node_type: str = ''
    group: str | None = None
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
    selected_tab: str = 'overview'
    yaml_text: str
    mermaid_text: str = 'graph TD\n'
    node_summaries: list[NodeSummaryView] = Field(default_factory=list)
    edge_summaries: list[EdgeSummaryView] = Field(default_factory=list)
    selected_node_editor: NodeEditorView | None = None
    edge_editor: EdgeEditorView = Field(default_factory=EdgeEditorView)
    validation_status: str = 'valid'
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    is_dirty: bool = False

