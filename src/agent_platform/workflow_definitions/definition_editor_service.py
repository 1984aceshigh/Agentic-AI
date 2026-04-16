from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml


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
            self._apply_optional_config_text(config, 'prompt', node_payload.get('llm_prompt'))
            self._apply_optional_config_text(config, 'input_definition', node_payload.get('llm_input_definition'))
            self._apply_optional_config_text(config, 'output_format', node_payload.get('llm_output_format'))
            if config:
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
        return lowered in {'llm_generate', 'llm_review'}

    def _apply_optional_config_text(self, config: dict[str, Any], key: str, raw_value: Any) -> None:
        if raw_value is None:
            return
        normalized = self._optional_text(raw_value)
        if normalized is None:
            config.pop(key, None)
            return
        config[key] = normalized

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
