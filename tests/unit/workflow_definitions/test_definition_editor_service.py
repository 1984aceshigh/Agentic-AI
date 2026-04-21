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
            'node_type': 'llm',
            'llm_prompt': 'Write a short answer',
            'llm_input_definition': 'topic: string',
            'llm_output_format': 'json',
        },
    )

    parsed = yaml.safe_load(updated)
    writer = next(node for node in parsed['nodes'] if node.get('id') == 'writer')
    assert writer['config']['task'] == 'generate'
    assert writer['config']['prompt'] == 'Write a short answer'
    assert writer['config']['input_definition'] == 'topic: string'
    assert writer['config']['output_format'] == 'json'


def test_add_llm_node_output_format_alias_plain_text_is_normalized_to_text() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'writer_text',
            'node_name': 'Writer Text',
            'node_type': 'llm',
            'llm_output_format': 'plain text',
        },
    )

    parsed = yaml.safe_load(updated)
    writer = next(node for node in parsed['nodes'] if node.get('id') == 'writer_text')
    assert writer['config']['output_format'] == 'text'


def test_add_llm_node_invalid_output_format_raises_value_error() -> None:
    service = DefinitionEditorService()

    try:
        service.add_node(
            SAMPLE_YAML,
            {
                'node_id': 'writer_invalid_fmt',
                'node_name': 'Writer Invalid Fmt',
                'node_type': 'llm',
                'llm_output_format': 'xml',
            },
        )
    except ValueError as exc:
        assert 'llm_output_format must be one of' in str(exc)
    else:
        raise AssertionError('Expected ValueError')


def test_add_llm_node_llm_task_is_saved_into_config_task():
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'assessor',
            'node_name': 'Assessor',
            'node_type': 'llm',
            'llm_task': 'assessment',
        },
    )

    parsed = yaml.safe_load(updated)
    assessor = next(node for node in parsed['nodes'] if node.get('id') == 'assessor')
    assert assessor['config']['task'] == 'assessment'


def test_add_llm_node_extended_task_configs_are_saved() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'extractor',
            'node_name': 'Extractor',
            'node_type': 'llm',
            'llm_task': 'extract',
            'llm_temperature': '0.3',
            'llm_extract_fields': 'company_name\ninvoice_no',
            'llm_extract_output_format': 'yaml',
            'llm_assessment_options': 'pass,rework',
            'llm_assessment_routes': 'pass: publish\nrework: rewrite',
        },
    )

    parsed = yaml.safe_load(updated)
    extractor = next(node for node in parsed['nodes'] if node.get('id') == 'extractor')
    assert extractor['config']['temperature'] == 0.3
    assert extractor['config']['extract_fields'] == ['company_name', 'invoice_no']
    assert extractor['config']['extract_output_format'] == 'yaml'
    assert extractor['config']['assessment_options'] == ['pass', 'rework']
    assert extractor['config']['assessment_routes'] == {'pass': 'publish', 'rework': 'rewrite'}


def test_add_llm_node_assessment_defaults_temperature_to_zero() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'assess_default_temp',
            'node_name': 'Assess Default Temp',
            'node_type': 'llm',
            'llm_task': 'assessment',
        },
    )

    parsed = yaml.safe_load(updated)
    node = next(item for item in parsed['nodes'] if item.get('id') == 'assess_default_temp')
    assert node['config']['temperature'] == 0.0


def test_add_llm_node_extract_defaults_output_format_to_json() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'extract_default_format',
            'node_name': 'Extract Default Format',
            'node_type': 'llm',
            'llm_task': 'extract',
        },
    )

    parsed = yaml.safe_load(updated)
    node = next(item for item in parsed['nodes'] if item.get('id') == 'extract_default_format')
    assert node['config']['extract_output_format'] == 'json'


def test_set_outgoing_edges_replaces_existing_outgoing_edges_for_node():
    service = DefinitionEditorService()

    updated = service.set_outgoing_edges(
        SAMPLE_YAML,
        from_node_id='start',
        to_node_ids=['end'],
    )

    parsed = yaml.safe_load(updated)
    assert parsed['edges'] == [{'from': 'start', 'to': 'end'}]


def test_set_outgoing_edges_can_clear_outgoing_edges_for_node():
    service = DefinitionEditorService()

    updated = service.set_outgoing_edges(
        SAMPLE_YAML,
        from_node_id='start',
        to_node_ids=[],
    )

    parsed = yaml.safe_load(updated)
    assert parsed['edges'] == []


def test_set_assessment_routes_updates_config_and_syncs_outgoing_edges() -> None:
    service = DefinitionEditorService()
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: judge
    name: Judge
    type: llm
    config:
      task: assessment
  - id: node_true
    name: Node True
    type: llm
  - id: node_false
    name: Node False
    type: llm
edges: []
"""

    updated = service.set_assessment_routes(
        yaml_text,
        from_node_id='judge',
        routes={'true': 'node_true', 'false': 'node_false'},
    )

    parsed = yaml.safe_load(updated)
    judge = next(item for item in parsed['nodes'] if item.get('id') == 'judge')
    assert judge['config']['assessment_routes'] == {'true': 'node_true', 'false': 'node_false'}
    assert {'from': 'judge', 'to': 'node_true'} in parsed['edges']
    assert {'from': 'judge', 'to': 'node_false'} in parsed['edges']


def test_update_node_can_clear_existing_group_when_group_field_is_blank():
    service = DefinitionEditorService()
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: review
    name: Review
    type: llm_review
    group: quality
edges: []
"""

    updated = service.update_node(
        yaml_text,
        'review',
        {
            'node_id': 'review',
            'node_name': 'Review',
            'node_type': 'llm_review',
            'group': '',
        },
    )

    parsed = yaml.safe_load(updated)
    review_node = next(node for node in parsed['nodes'] if node.get('id') == 'review')
    assert 'group' not in review_node


def test_add_human_gate_node_human_gate_task_is_saved_into_config_task() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'entry',
            'node_name': 'Entry Input',
            'node_type': 'human_gate',
            'human_gate_task': 'entry_input',
        },
    )

    parsed = yaml.safe_load(updated)
    node = next(item for item in parsed['nodes'] if item.get('id') == 'entry')
    assert node['config']['task'] == 'entry_input'


def test_update_human_gate_node_human_gate_task_is_updated() -> None:
    service = DefinitionEditorService()
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: review
    name: Review
    type: human_gate
    config:
      task: approval
edges: []
"""

    updated = service.update_node(
        yaml_text,
        'review',
        {
            'node_id': 'review',
            'node_name': 'Review',
            'node_type': 'human_gate',
            'human_gate_task': 'human_task',
        },
    )

    parsed = yaml.safe_load(updated)
    review_node = next(node for node in parsed['nodes'] if node.get('id') == 'review')
    assert review_node['config']['task'] == 'human_task'


def test_add_human_gate_approval_defaults_options_to_approve_reject() -> None:
    service = DefinitionEditorService()

    updated = service.add_node(
        SAMPLE_YAML,
        {
            'node_id': 'gate',
            'node_name': 'Gate',
            'node_type': 'human_gate',
            'human_gate_task': 'approval',
        },
    )

    parsed = yaml.safe_load(updated)
    gate = next(item for item in parsed['nodes'] if item.get('id') == 'gate')
    assert gate['config']['task'] == 'approval'
    assert gate['config']['approval_options'] == ['承認', '否認']


def test_set_human_gate_approval_routes_updates_config_and_syncs_outgoing_edges() -> None:
    service = DefinitionEditorService()
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: gate
    name: Gate
    type: human_gate
    config:
      task: approval
      approval_options:
        - 承認
        - 否認
  - id: publish
    name: Publish
    type: llm
  - id: revise
    name: Revise
    type: llm
edges: []
"""

    updated = service.set_human_gate_approval_routes(
        yaml_text,
        from_node_id='gate',
        routes={'承認': 'publish', '否認': 'revise'},
    )

    parsed = yaml.safe_load(updated)
    gate = next(item for item in parsed['nodes'] if item.get('id') == 'gate')
    assert gate['config']['approval_routes'] == {'承認': 'publish', '否認': 'revise'}
    assert {'from': 'gate', 'to': 'publish'} in parsed['edges']
    assert {'from': 'gate', 'to': 'revise'} in parsed['edges']
