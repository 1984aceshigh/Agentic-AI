from pathlib import Path

from agent_platform.workflow_definitions import FileWorkflowDefinitionRepository, WorkflowDefinitionDocument


SAMPLE_YAML = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
version: 0.1.0
nodes:
  - id: start
    name: Start
    type: llm_generate
edges: []
"""


def test_save_and_get_document(tmp_path: Path):
    repo = FileWorkflowDefinitionRepository(tmp_path / 'workflow_definitions')
    document = WorkflowDefinitionDocument(
        workflow_id='sample_workflow',
        workflow_name='Sample Workflow',
        version='0.1.0',
        description=None,
        yaml_text=SAMPLE_YAML,
        updated_at=None,
        is_archived=False,
        source_path=None,
    )
    repo.save(document)
    loaded = repo.get('sample_workflow')
    assert loaded.workflow_id == 'sample_workflow'
    assert 'Sample Workflow' in loaded.yaml_text


def test_archive_moves_document(tmp_path: Path):
    repo = FileWorkflowDefinitionRepository(tmp_path / 'workflow_definitions')
    document = WorkflowDefinitionDocument(
        workflow_id='sample_workflow',
        workflow_name='Sample Workflow',
        version='0.1.0',
        description=None,
        yaml_text=SAMPLE_YAML,
        updated_at=None,
        is_archived=False,
        source_path=None,
    )
    repo.save(document)
    archived = repo.archive('sample_workflow')
    assert archived.is_archived is True
    assert repo.list_active() == []
