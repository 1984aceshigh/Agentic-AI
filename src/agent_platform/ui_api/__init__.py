try:
    from .app import create_app
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
    _create_app_import_error = exc

    def create_app(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError(
            "create_app を利用するには Flask が必要です。環境に flask をインストールしてください。"
        ) from _create_app_import_error
from .definition_view_models import (
    EdgeEditorView,
    EdgeSummaryView,
    GraphEditorView,
    NodeEditorView,
    NodeSummaryView,
    WorkflowDefinitionSummaryView,
)
try:
    from .dependencies import (
        HumanGateService,
        RerunService,
        get_definition_editor_service,
        get_definition_read_model_service,
        get_definition_validation_service,
        get_workflow_definition_service,
        set_latest_execution_ids,
        set_workflow_graphs,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    HumanGateService = object  # type: ignore[assignment]
    RerunService = object  # type: ignore[assignment]

    def get_definition_editor_service(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")

    def get_definition_read_model_service(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")

    def get_definition_validation_service(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")

    def get_workflow_definition_service(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")

    def set_latest_execution_ids(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")

    def set_workflow_graphs(*args, **kwargs):  # type: ignore[no-redef]
        raise ModuleNotFoundError("UI dependencies を利用するには Flask が必要です。")
from .read_model_service import ReadModelService
from .view_models import (
    ExecutionArtifactsView,
    GraphView,
    NodeCardView,
    NodeDetailView,
    WorkflowSummaryView,
)
from agent_platform.workflow_definitions import (
    DefinitionEditorService,
    DefinitionValidationService,
    FileWorkflowDefinitionRepository,
    WorkflowDefinitionDocument,
    WorkflowDefinitionMeta,
    WorkflowDefinitionService,
)

__all__ = [
    'create_app',
    'ReadModelService',
    'HumanGateService',
    'RerunService',
    'set_workflow_graphs',
    'set_latest_execution_ids',
    'WorkflowSummaryView',
    'NodeCardView',
    'NodeDetailView',
    'GraphView',
    'ExecutionArtifactsView',
    'WorkflowDefinitionSummaryView',
    'GraphEditorView',
    'NodeSummaryView',
    'EdgeSummaryView',
    'NodeEditorView',
    'EdgeEditorView',
    'WorkflowDefinitionService',
    'DefinitionValidationService',
    'DefinitionEditorService',
    'FileWorkflowDefinitionRepository',
    'WorkflowDefinitionDocument',
    'WorkflowDefinitionMeta',
    'get_workflow_definition_service',
    'get_definition_validation_service',
    'get_definition_editor_service',
    'get_definition_read_model_service',
]
