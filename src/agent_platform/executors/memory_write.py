from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult
from agent_platform.integrations.memory_contracts import (
    MemoryScope,
    MemoryWriteRequest,
)
from agent_platform.integrations.profile_resolver import (
    ProfileResolutionError,
    ProfileResolver,
)


def _get_attr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_scope(value: Any) -> MemoryScope:
    if isinstance(value, MemoryScope):
        return value
    if isinstance(value, str):
        return MemoryScope(value)
    raise ValueError(f"Unsupported memory scope: {value!r}")


def _build_content_from_config(
    node_config: Mapping[str, Any],
    context: Any,
) -> dict[str, Any]:
    content_template = node_config.get("content_template")
    if isinstance(content_template, dict):
        return dict(content_template)

    return {
        "workflow_id": _get_attr_or_key(context, "workflow_id"),
        "execution_id": _get_attr_or_key(context, "execution_id"),
        "node_id": _get_attr_or_key(context, "current_node_id"),
    }


@dataclass(slots=True)
class MemoryWriteExecutor(BaseNodeExecutor):
    profile_resolver: ProfileResolver
    stores_by_profile: Mapping[str, Any]

    supported_node_types = ("memory_write",)

    def execute(self, node: Any, context: Any) -> ExecutorResult:
        workflow_spec = _get_attr_or_key(context, "workflow_spec")
        node_config = _get_attr_or_key(node, "config", {}) or {}

        try:
            self.profile_resolver.resolve_profile_for_node(
                spec=workflow_spec,
                node=node,
            )
        except ProfileResolutionError as exc:
            return ExecutorResult(
                status="FAILED",
                output={},
                error_message=str(exc),
            )

        profile_name = node_config.get("memory_profile")
        store = self.stores_by_profile.get(profile_name)
        if store is None:
            return ExecutorResult(
                status="FAILED",
                output={},
                error_message=f"Memory store not found for profile: {profile_name}",
            )

        raw_scope = node_config.get("scope")
        if raw_scope is None:
            return ExecutorResult(
                status="FAILED",
                output={},
                error_message="memory_write requires config.scope",
            )

        try:
            scope = _to_scope(raw_scope)
        except ValueError as exc:
            return ExecutorResult(
                status="FAILED",
                output={},
                error_message=str(exc),
            )

        request = MemoryWriteRequest(
            scope=scope,
            workflow_id=node_config.get("workflow_id")
            or _get_attr_or_key(context, "workflow_id"),
            execution_id=node_config.get("execution_id")
            or _get_attr_or_key(context, "execution_id"),
            tags=list(node_config.get("tags", [])),
            content=_build_content_from_config(node_config, context),
        )

        record = store.write(request)

        return ExecutorResult(
            status="SUCCEEDED",
            output={
                "record_id": record.record_id,
                "scope": record.scope.value,
                "workflow_id": record.workflow_id,
                "execution_id": record.execution_id,
                "tags": record.tags,
            },
            error_message=None,
        )


__all__ = ["MemoryWriteExecutor"]