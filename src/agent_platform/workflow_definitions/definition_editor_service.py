from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml


LLM_TASK_CHOICES = {'generate', 'assessment', 'extract'}
EXTRACT_OUTPUT_FORMAT_CHOICES = {'json', 'yaml', 'markdown', 'plain_text'}
LLM_OUTPUT_FORMAT_CHOICES = {
    'json',
    'yaml',
    'markdown',
    'mermaid',
    'text',
    'markdown_json',
    'markdown_yaml',
    'markdown_mermaid',
}
HUMAN_GATE_TASK_CHOICES = {'entry_input', 'human_task', 'approval'}
DEFAULT_APPROVAL_OPTIONS = ['承認', '否認']


class DefinitionEditorService:
    def add_node(self, yaml_text: str, node_payload: dict[str, Any]) -> str:
        parsed = self._parse(yaml_text)
        nodes = parsed.setdefault('nodes', [])
        node_id = self._require_str(node_payload.get('node_id'), 'node_id')
        if self._find_node(parsed, node_id) is not None:
            raise ValueError(f'Node already exists: {node_id}')
        node_object = self._build_node_object(None, node_payload)
        if isinstance(nodes, list):
            nodes.append(node_object)
        elif isinstance(nodes, dict):
            nodes[node_id] = {k: v for k, v in node_object.items() if k not in {'id', 'node_id'}}
        else:
            raise ValueError('nodes must be either a list or a mapping.')
        return self._dump(parsed)

    def update_node(self, yaml_text: str, node_id: str, node_payload: dict[str, Any]) -> str:
        parsed = self._parse(yaml_text)
        nodes = parsed.get('nodes')
        existing = self._find_node(parsed, node_id)
        if existing is None or nodes is None:
            raise KeyError(f'Unknown node_id: {node_id}')

        updated_node = self._build_node_object(existing, node_payload)
        if isinstance(nodes, list):
            for index, item in enumerate(nodes):
                if isinstance(item, dict) and self._extract_node_id(item, fallback_index=index) == node_id:
                    nodes[index] = updated_node
                    return self._dump(parsed)
        elif isinstance(nodes, dict):
            new_node_id = self._require_str(node_payload.get('node_id') or node_id, 'node_id')
            nodes.pop(node_id, None)
            nodes[new_node_id] = {k: v for k, v in updated_node.items() if k not in {'id', 'node_id'}}
            self._rewrite_edge_references(parsed, old_node_id=node_id, new_node_id=new_node_id)
            return self._dump(parsed)
        raise KeyError(f'Unknown node_id: {node_id}')

    def delete_node(self, yaml_text: str, node_id: str) -> str:
        parsed = self._parse(yaml_text)
        if self._has_related_edges(parsed, node_id):
            raise ValueError(f'Cannot delete node with connected edges: {node_id}')
        nodes = parsed.get('nodes')
        if isinstance(nodes, list):
            parsed['nodes'] = [node for index, node in enumerate(nodes) if not (isinstance(node, dict) and self._extract_node_id(node, fallback_index=index) == node_id)]
            return self._dump(parsed)
        if isinstance(nodes, dict):
            if node_id not in nodes:
                raise KeyError(f'Unknown node_id: {node_id}')
            nodes.pop(node_id)
            return self._dump(parsed)
        raise ValueError('nodes must be either a list or a mapping.')

    def duplicate_node(self, yaml_text: str, node_id: str, new_node_id: str) -> str:
        parsed = self._parse(yaml_text)
        existing = self._find_node(parsed, node_id)
        if existing is None:
            raise KeyError(f'Unknown node_id: {node_id}')
        copied = deepcopy(existing)
        copied['node_id'] = new_node_id
        copied['id'] = new_node_id
        copied.setdefault('name', new_node_id)
        return self.add_node(self._dump(parsed), copied)

    def add_edge(self, yaml_text: str, from_node_id: str, to_node_id: str, edge_payload: dict[str, Any]) -> str:
        parsed = self._parse(yaml_text)
        self._ensure_node_exists(parsed, from_node_id)
        self._ensure_node_exists(parsed, to_node_id)
        edges = parsed.setdefault('edges', [])
        if not isinstance(edges, list):
            raise ValueError('edges must be a list.')
        advanced = self._parse_yaml_fragment(edge_payload.get('advanced_yaml_fragment'))
        edge = {k: v for k, v in advanced.items() if k not in {'from', 'to', 'source', 'target', 'label'}}
        edge['from'] = from_node_id
        edge['to'] = to_node_id
        label = self._optional_text(edge_payload.get('label'))
        if label is not None:
            edge['label'] = label
        edges.append(edge)
        return self._dump(parsed)

    def set_outgoing_edges(self, yaml_text: str, from_node_id: str, to_node_ids: list[str]) -> str:
        parsed = self._parse(yaml_text)
        self._ensure_node_exists(parsed, from_node_id)
        edges = parsed.setdefault('edges', [])
        if not isinstance(edges, list):
            raise ValueError('edges must be a list.')

        normalized_targets: list[str] = []
        for node_id in to_node_ids:
            target_id = self._optional_text(node_id)
            if target_id is None or target_id == from_node_id:
                continue
            if target_id in normalized_targets:
                continue
            self._ensure_node_exists(parsed, target_id)
            normalized_targets.append(target_id)

        remaining_edges: list[Any] = []
        for edge in edges:
            if not isinstance(edge, dict):
                remaining_edges.append(edge)
                continue
            source = str(edge.get('from') or edge.get('source') or '')
            if source == from_node_id:
                continue
            remaining_edges.append(edge)

        for target_id in normalized_targets:
            remaining_edges.append({'from': from_node_id, 'to': target_id})

        parsed['edges'] = remaining_edges
        return self._dump(parsed)

    def set_assessment_routes(self, yaml_text: str, from_node_id: str, routes: dict[str, Any]) -> str:
        parsed = self._parse(yaml_text)
        node = self._find_node(parsed, from_node_id)
        if node is None:
            raise KeyError(f'Unknown node_id: {from_node_id}')

        node_type = str(node.get('type') or node.get('node_type') or '')
        if not self._is_llm_node_type(node_type):
            raise ValueError('assessment routes can only be set for llm nodes.')

        config = node.get('config') if isinstance(node.get('config'), dict) else {}
        config['task'] = self._normalize_llm_task(config.get('task'))
        if config['task'] != 'assessment':
            raise ValueError('assessment routes can only be set when config.task is assessment.')

        normalized_routes: dict[str, Any] = {}
        for option, target_node_ids in (routes or {}).items():
            option_text = self._optional_text(option)
            if option_text is None:
                continue
            normalized_targets: list[str] = []
            if isinstance(target_node_ids, list):
                raw_target_ids = target_node_ids
            else:
                raw_target_ids = [target_node_ids]
            for target_node_id in raw_target_ids:
                node_id_text = self._optional_text(target_node_id)
                if node_id_text is None or node_id_text == from_node_id:
                    continue
                self._ensure_node_exists(parsed, node_id_text)
                if node_id_text not in normalized_targets:
                    normalized_targets.append(node_id_text)
            if not normalized_targets:
                continue
            normalized_routes[option_text] = (
                normalized_targets[0] if len(normalized_targets) == 1 else normalized_targets
            )

        if normalized_routes:
            config['assessment_routes'] = normalized_routes
        else:
            config.pop('assessment_routes', None)
        node['config'] = config

        parsed = self._replace_node(parsed, from_node_id, node)
        target_ids: list[str] = []
        for route_target in normalized_routes.values():
            if isinstance(route_target, list):
                for node_id in route_target:
                    if node_id not in target_ids:
                        target_ids.append(node_id)
            elif isinstance(route_target, str) and route_target not in target_ids:
                target_ids.append(route_target)
        return self.set_outgoing_edges(self._dump(parsed), from_node_id, target_ids)

    def set_human_gate_approval_routes(self, yaml_text: str, from_node_id: str, routes: dict[str, Any]) -> str:
        parsed = self._parse(yaml_text)
        node = self._find_node(parsed, from_node_id)
        if node is None:
            raise KeyError(f'Unknown node_id: {from_node_id}')

        node_type = str(node.get('type') or node.get('node_type') or '')
        if not self._is_human_gate_node_type(node_type):
            raise ValueError('approval routes can only be set for human_gate nodes.')

        config = node.get('config') if isinstance(node.get('config'), dict) else {}
        config['task'] = self._normalize_human_gate_task(config.get('task'))
        if config['task'] != 'approval':
            raise ValueError('approval routes can only be set when config.task is approval.')

        normalized_routes: dict[str, Any] = {}
        for option, target_node_ids in (routes or {}).items():
            option_text = self._optional_text(option)
            if option_text is None:
                continue
            normalized_targets: list[str] = []
            if isinstance(target_node_ids, list):
                raw_target_ids = target_node_ids
            else:
                raw_target_ids = [target_node_ids]
            for target_node_id in raw_target_ids:
                node_id_text = self._optional_text(target_node_id)
                if node_id_text is None or node_id_text == from_node_id:
                    continue
                self._ensure_node_exists(parsed, node_id_text)
                if node_id_text not in normalized_targets:
                    normalized_targets.append(node_id_text)
            if not normalized_targets:
                continue
            normalized_routes[option_text] = (
                normalized_targets[0] if len(normalized_targets) == 1 else normalized_targets
            )

        if normalized_routes:
            config['approval_routes'] = normalized_routes
        else:
            config.pop('approval_routes', None)
        node['config'] = config

        parsed = self._replace_node(parsed, from_node_id, node)
        target_ids: list[str] = []
        for route_target in normalized_routes.values():
            if isinstance(route_target, list):
                for node_id in route_target:
                    if node_id not in target_ids:
                        target_ids.append(node_id)
            elif isinstance(route_target, str) and route_target not in target_ids:
                target_ids.append(route_target)
        return self.set_outgoing_edges(self._dump(parsed), from_node_id, target_ids)

    def delete_edge(self, yaml_text: str, from_node_id: str, to_node_id: str) -> str:
        parsed = self._parse(yaml_text)
        edges = parsed.get('edges')
        if not isinstance(edges, list):
            raise ValueError('edges must be a list.')
        filtered = []
        removed = False
        for edge in edges:
            if not isinstance(edge, dict):
                filtered.append(edge)
                continue
            source = edge.get('from') or edge.get('source')
            target = edge.get('to') or edge.get('target')
            if str(source) == from_node_id and str(target) == to_node_id and not removed:
                removed = True
                continue
            filtered.append(edge)
        if not removed:
            raise KeyError(f'Unknown edge: {from_node_id} -> {to_node_id}')
        parsed['edges'] = filtered
        return self._dump(parsed)

    def _build_node_object(self, existing: dict[str, Any] | None, node_payload: dict[str, Any]) -> dict[str, Any]:
        current = deepcopy(existing) if existing is not None else {}
        advanced = self._parse_yaml_fragment(node_payload.get('advanced_yaml_fragment'))
        node_id = self._require_str(node_payload.get('node_id') or current.get('node_id') or current.get('id'), 'node_id')
        node_name = self._require_str(node_payload.get('node_name') or current.get('name') or current.get('display_name') or node_id, 'node_name')
        node_type = self._require_str(node_payload.get('node_type') or current.get('node_type') or current.get('type'), 'node_type')
        has_group_field = 'group' in node_payload
        group = self._optional_text(node_payload.get('group'))

        preserved = {
            k: v
            for k, v in current.items()
            if k not in {'id', 'node_id', 'name', 'display_name', 'type', 'node_type', 'group'}
        }
        preserved.update({k: v for k, v in advanced.items() if k not in {'id', 'node_id', 'name', 'display_name', 'type', 'node_type', 'group'}})

        id_key = 'id' if existing is None or 'id' in current else 'node_id'
        type_key = 'type' if existing is None or 'type' in current else 'node_type'
        name_key = 'name' if existing is None or 'name' in current else 'display_name'

        node = dict(preserved)
        node[id_key] = node_id
        node[name_key] = node_name
        node[type_key] = node_type

        if self._is_llm_node_type(node_type):
            config = node.get('config')
            if not isinstance(config, dict):
                config = {}
            if 'llm_task' in node_payload:
                self._apply_llm_task(config, node_payload.get('llm_task'))
            elif 'task' in config:
                config['task'] = self._normalize_llm_task(config.get('task'))
            else:
                config['task'] = 'generate'
            self._apply_optional_config_text(config, 'prompt', node_payload.get('llm_prompt'))
            self._apply_optional_config_text(config, 'input_definition', node_payload.get('llm_input_definition'))
            self._apply_optional_llm_output_format(config, node_payload.get('llm_output_format'))
            self._apply_optional_config_float(config, 'temperature', node_payload.get('llm_temperature'))
            self._apply_optional_assessment_options(config, node_payload.get('llm_assessment_options'))
            self._apply_optional_assessment_routes(config, node_payload.get('llm_assessment_routes'))
            self._apply_optional_extract_fields(config, node_payload.get('llm_extract_fields'))
            self._apply_optional_extract_output_format(config, node_payload.get('llm_extract_output_format'))

            current_task = self._normalize_llm_task(config.get('task'))
            if current_task == 'assessment':
                config['temperature'] = 0.0
            elif current_task == 'extract' and node_payload.get('llm_temperature') is None:
                config['temperature'] = 0.0
            if current_task == 'extract' and 'extract_output_format' not in config:
                config['extract_output_format'] = 'json'

            if config:
                node['config'] = config

        if self._is_human_gate_node_type(node_type):
            config = node.get('config')
            if not isinstance(config, dict):
                config = {}
            if 'human_gate_task' in node_payload:
                self._apply_human_gate_task(config, node_payload.get('human_gate_task'))
            elif 'task' in config:
                config['task'] = self._normalize_human_gate_task(config.get('task'))
            else:
                config['task'] = 'approval'
            self._apply_optional_human_gate_approval_options(config, node_payload.get('human_gate_approval_options'))
            self._apply_optional_human_gate_approval_routes(config, node_payload.get('human_gate_approval_routes'))
            self._apply_default_human_gate_approval_options(config)
            node['config'] = config

        if has_group_field:
            if group is not None:
                node['group'] = group
            else:
                node.pop('group', None)
        elif existing is not None and 'group' in current:
            node['group'] = current['group']
        return node

    def _is_llm_node_type(self, node_type: str) -> bool:
        lowered = str(node_type).strip().lower()
        return lowered == 'llm'

    def _is_human_gate_node_type(self, node_type: str) -> bool:
        lowered = str(node_type).strip().lower()
        return lowered == 'human_gate'

    def _apply_optional_config_text(self, config: dict[str, Any], key: str, raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop(key, None)
            return
        config[key] = normalized

    def _apply_llm_task(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config['task'] = 'generate'
            return
        config['task'] = self._normalize_llm_task(normalized)

    def _apply_human_gate_task(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config['task'] = 'approval'
            return
        config['task'] = self._normalize_human_gate_task(normalized)

    def _apply_optional_human_gate_approval_options(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop('approval_options', None)
            return
        options = [item.strip() for item in normalized.replace(',', '\n').splitlines() if item.strip()]
        if options:
            config['approval_options'] = options
        else:
            config.pop('approval_options', None)

    def _apply_optional_human_gate_approval_routes(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop('approval_routes', None)
            return
        loaded = yaml.safe_load(normalized)
        if loaded is None:
            config.pop('approval_routes', None)
            return
        if not isinstance(loaded, dict):
            raise ValueError('human_gate_approval_routes must be a YAML mapping.')
        routes: dict[str, Any] = {}
        for option, node_id in loaded.items():
            option_text = str(option).strip()
            if not option_text:
                continue
            if isinstance(node_id, list):
                node_ids = [str(item).strip() for item in node_id if str(item).strip()]
                if not node_ids:
                    continue
                routes[option_text] = node_ids[0] if len(node_ids) == 1 else node_ids
                continue
            node_id_text = str(node_id).strip()
            if node_id_text:
                routes[option_text] = node_id_text
        if routes:
            config['approval_routes'] = routes
        else:
            config.pop('approval_routes', None)

    def _apply_default_human_gate_approval_options(self, config: dict[str, Any]) -> None:
        task = self._normalize_human_gate_task(config.get('task'))
        if task != 'approval':
            return
        options = config.get('approval_options')
        if isinstance(options, list) and any(str(item).strip() for item in options):
            return
        config['approval_options'] = list(DEFAULT_APPROVAL_OPTIONS)

    def _apply_optional_config_float(self, config: dict[str, Any], key: str, raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop(key, None)
            return
        config[key] = float(normalized)

    def _apply_optional_assessment_options(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop('assessment_options', None)
            return
        options = [item.strip() for item in normalized.replace(',', '\n').splitlines() if item.strip()]
        if options:
            config['assessment_options'] = options
        else:
            config.pop('assessment_options', None)

    def _apply_optional_assessment_routes(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop('assessment_routes', None)
            return
        loaded = yaml.safe_load(normalized)
        if loaded is None:
            config.pop('assessment_routes', None)
            return
        if not isinstance(loaded, dict):
            raise ValueError('llm_assessment_routes must be a YAML mapping.')
        routes: dict[str, Any] = {}
        for option, node_id in loaded.items():
            option_text = str(option).strip()
            if not option_text:
                continue
            if isinstance(node_id, list):
                node_ids = [str(item).strip() for item in node_id if str(item).strip()]
                if not node_ids:
                    continue
                routes[option_text] = node_ids[0] if len(node_ids) == 1 else node_ids
                continue
            node_id_text = str(node_id).strip()
            if node_id_text:
                routes[option_text] = node_id_text
        if routes:
            config['assessment_routes'] = routes
        else:
            config.pop('assessment_routes', None)

    def _apply_optional_extract_fields(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop('extract_fields', None)
            return
        fields = [item.strip() for item in normalized.replace(',', '\n').splitlines() if item.strip()]
        if fields:
            config['extract_fields'] = fields
        else:
            config.pop('extract_fields', None)

    def _apply_optional_extract_output_format(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = str(raw_value or '').strip().lower()
        if not normalized:
            config.pop('extract_output_format', None)
            return
        if normalized == 'plain text':
            normalized = 'plain_text'
        if normalized not in EXTRACT_OUTPUT_FORMAT_CHOICES:
            raise ValueError('llm_extract_output_format must be one of json/yaml/markdown/plain_text.')
        config['extract_output_format'] = normalized

    def _apply_optional_llm_output_format(self, config: dict[str, Any], raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._normalize_llm_output_format(raw_value)
        if normalized is None:
            config.pop('output_format', None)
            return
        config['output_format'] = normalized

    def _normalize_llm_output_format(self, raw_value: Any) -> str | None:
        normalized = str(raw_value or '').strip().lower().replace(' ', '_').replace('-', '_')
        if not normalized:
            return None
        alias_map = {
            'plain_text': 'text',
            'md_json': 'markdown_json',
            'md_yaml': 'markdown_yaml',
            'md_mermaid': 'markdown_mermaid',
        }
        normalized = alias_map.get(normalized, normalized)
        if normalized not in LLM_OUTPUT_FORMAT_CHOICES:
            raise ValueError(
                'llm_output_format must be one of '
                'json/yaml/markdown/mermaid/text/markdown_json/markdown_yaml/markdown_mermaid.'
            )
        return normalized

    def _normalize_llm_task(self, raw_task: Any) -> str:
        normalized = str(raw_task or '').strip().lower()
        if normalized in LLM_TASK_CHOICES:
            return normalized
        if normalized in {'review', 'classify', 'judge'}:
            return 'assessment'
        return 'generate'

    def _normalize_human_gate_task(self, raw_task: Any) -> str:
        normalized = str(raw_task or '').strip().lower()
        if normalized in HUMAN_GATE_TASK_CHOICES:
            return normalized
        if normalized == 'review':
            return 'human_task'
        return 'approval'

    def _parse(self, yaml_text: str) -> dict[str, Any]:
        parsed = yaml.safe_load(yaml_text) or {}
        if not isinstance(parsed, dict):
            raise ValueError('Workflow YAML must be a mapping at the top level.')
        return parsed

    def _dump(self, parsed: dict[str, Any]) -> str:
        return yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)

    def _parse_yaml_fragment(self, fragment: Any) -> dict[str, Any]:
        text = self._optional_text(fragment)
        if text is None:
            return {}
        loaded = yaml.safe_load(text)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError('Advanced YAML fragment must be a mapping.')
        return loaded

    def _find_node(self, parsed: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        nodes = parsed.get('nodes')
        if isinstance(nodes, list):
            for index, node in enumerate(nodes):
                if isinstance(node, dict) and self._extract_node_id(node, fallback_index=index) == node_id:
                    return deepcopy(node)
        elif isinstance(nodes, dict):
            payload = nodes.get(node_id)
            if isinstance(payload, dict):
                node = deepcopy(payload)
                node.setdefault('id', node_id)
                return node
        return None

    def _replace_node(self, parsed: dict[str, Any], node_id: str, updated_node: dict[str, Any]) -> dict[str, Any]:
        nodes = parsed.get('nodes')
        if isinstance(nodes, list):
            for index, node in enumerate(nodes):
                if isinstance(node, dict) and self._extract_node_id(node, fallback_index=index) == node_id:
                    nodes[index] = updated_node
                    return parsed
            raise KeyError(f'Unknown node_id: {node_id}')
        if isinstance(nodes, dict):
            if node_id not in nodes:
                raise KeyError(f'Unknown node_id: {node_id}')
            nodes[node_id] = {k: v for k, v in updated_node.items() if k not in {'id', 'node_id'}}
            return parsed
        raise ValueError('nodes must be either a list or a mapping.')

    def _extract_node_id(self, node: dict[str, Any], *, fallback_index: int | None = None) -> str:
        node_id = node.get('node_id') or node.get('id')
        if node_id is not None:
            return str(node_id)
        if fallback_index is not None:
            return f'node_{fallback_index}'
        raise ValueError('Node is missing id/node_id.')

    def _ensure_node_exists(self, parsed: dict[str, Any], node_id: str) -> None:
        if self._find_node(parsed, node_id) is None:
            raise KeyError(f'Unknown node_id: {node_id}')

    def _has_related_edges(self, parsed: dict[str, Any], node_id: str) -> bool:
        edges = parsed.get('edges')
        if not isinstance(edges, list):
            return False
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get('from') or edge.get('source') or '')
            target = str(edge.get('to') or edge.get('target') or '')
            if source == node_id or target == node_id:
                return True
        return False

    def _rewrite_edge_references(self, parsed: dict[str, Any], *, old_node_id: str, new_node_id: str) -> None:
        edges = parsed.get('edges')
        if not isinstance(edges, list):
            return
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if str(edge.get('from') or edge.get('source') or '') == old_node_id:
                if 'from' in edge:
                    edge['from'] = new_node_id
                elif 'source' in edge:
                    edge['source'] = new_node_id
            if str(edge.get('to') or edge.get('target') or '') == old_node_id:
                if 'to' in edge:
                    edge['to'] = new_node_id
                elif 'target' in edge:
                    edge['target'] = new_node_id

    def _require_str(self, value: Any, field_name: str) -> str:
        text = self._optional_text(value)
        if text is None:
            raise ValueError(f'{field_name} is required.')
        return text

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
