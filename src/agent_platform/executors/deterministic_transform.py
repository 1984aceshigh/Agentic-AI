from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult


class DeterministicTransformExecutor(BaseNodeExecutor):
    """Minimal deterministic transform executor for MVP."""

    SUPPORTED_TRANSFORM_TYPES = {
        "pass_through",
        "json_extract",
        "merge_dict",
        "template_render",
    }

    def execute(self, context: Any, node: Any) -> ExecutorResult:
        try:
            prepared = self.prepare_input(context=context, node=node)
            config = prepared["node_config"]
            transform_type = config.get("transform_type")
            params = config.get("params", {}) or {}

            if transform_type not in self.SUPPORTED_TRANSFORM_TYPES:
                raise ValueError(f"Unsupported transform_type: {transform_type}")

            if transform_type == "pass_through":
                output = {"result": self._pass_through(prepared)}
            elif transform_type == "json_extract":
                output = {"result": self._json_extract(prepared, params)}
            elif transform_type == "merge_dict":
                output = {"result": self._merge_dict(prepared, params)}
            else:
                output = {"result": self._template_render(prepared, params)}

            return ExecutorResult(
                status="SUCCEEDED",
                output=output,
                logs=[f"deterministic_transform executed: {transform_type}"],
            )
        except Exception as exc:
            return self.handle_error(exc)

    def _pass_through(self, prepared: dict[str, Any]) -> Any:
        resolved_inputs = prepared["resolved_inputs"]
        if len(resolved_inputs) == 1:
            return next(iter(resolved_inputs.values()))
        if resolved_inputs:
            return resolved_inputs
        return prepared["global_inputs"]

    def _json_extract(self, prepared: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        fields = params.get("fields", []) or []
        source_key = params.get("source_key")
        source_payload = self._pick_source_payload(prepared, source_key)
        parsed = self._ensure_dict(source_payload)
        return {field: parsed[field] for field in fields if field in parsed}

    def _merge_dict(self, prepared: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for value in prepared["resolved_inputs"].values():
            if isinstance(value, Mapping):
                merged.update(dict(value))
        static_values = params.get("static_values", {}) or {}
        if isinstance(static_values, Mapping):
            merged.update(dict(static_values))
        return merged

    def _template_render(self, prepared: dict[str, Any], params: dict[str, Any]) -> str:
        template = params.get("template")
        if not template:
            raise ValueError("template_render requires params.template")

        values: dict[str, Any] = {}
        values.update(prepared["global_inputs"])
        for item in prepared["resolved_inputs"].values():
            if isinstance(item, Mapping):
                values.update(dict(item))
        explicit_values = params.get("values", {}) or {}
        if isinstance(explicit_values, Mapping):
            values.update(dict(explicit_values))

        return str(template).format_map(_SafeFormatDict(values))

    def _pick_source_payload(self, prepared: dict[str, Any], source_key: str | None) -> Any:
        resolved_inputs = prepared["resolved_inputs"]
        if source_key:
            if source_key not in resolved_inputs:
                raise KeyError(f"source_key not found in resolved_inputs: {source_key}")
            return resolved_inputs[source_key]
        if len(resolved_inputs) == 1:
            return next(iter(resolved_inputs.values()))
        raise ValueError("json_extract requires exactly one resolved input or params.source_key")

    def _ensure_dict(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, str):
            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                raise ValueError("json_extract source JSON must decode to an object")
            return parsed
        raise ValueError("json_extract source must be dict-like or JSON string")


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
