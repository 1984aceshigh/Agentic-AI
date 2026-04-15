from agent_platform.workflow_definitions import DefinitionEditorService
import yaml


SAMPLE_YAML = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: start
    name: Start
    type: llm_generate
  - id: end
    name: End
    type: deterministic_transform
edges:
  - from: start
    to: end
"""


def test_add_node_updates_yaml_text():
    service = DefinitionEditorService()
    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'review',
            'node_name': 'Review',
            'node_type': 'llm_review',
            'group': 'quality',
            'advanced_yaml_fragment': 'config:\n  score_threshold: 0.8\n',
        },
    )
    assert 'review' in updated
    assert 'score_threshold' in updated


def test_delete_node_with_edge_raises():
    service = DefinitionEditorService()
    try:
        service.delete_node(SAMPLE_YAML, 'start')
    except ValueError as exc:
        assert 'connected edges' in str(exc)
    else:
        raise AssertionError('Expected ValueError')


def test_add_llm_node_fields_are_saved_into_config():
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'writer',
            'node_name': 'Writer',
            'node_type': 'llm_generate',
            'llm_prompt': 'Write a short answer',
            'llm_input_definition': 'topic: string',
            'llm_output_format': 'json: {"answer": string}',
        },
    )

    parsed = yaml.safe_load(updated)
    writer = next(node for node in parsed['nodes'] if node.get('id') == 'writer')
    assert writer['config']['prompt'] == 'Write a short answer'
    assert writer['config']['input_definition'] == 'topic: string'
    assert writer['config']['output_format'] == 'json: {"answer": string}'
