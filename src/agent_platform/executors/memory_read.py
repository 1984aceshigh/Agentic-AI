from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor
from agent_platform.integrations.memory_contracts import MemoryQuery, MemoryScope, MemoryStore
from agent_platform.integrations.profile_resolver import ProfileResolver


class MemoryReadExecutor(BaseNodeExecutor):
    node_type = "memory_read"

    def __init__(
        self,
        *,
        stores_by_profile_name: Mapping[str, MemoryStore] | None = None,
        profile_resolver: ProfileResolver | None = None,
    ) -> None:
        self._stores_by_profile_name = dict(stores_by_profile_name or {})
        self._profile_resolver = profile_resolver or ProfileResolver()

    def prepare_input(self, *, spec: Any, node: Any, context: Any | None = None) -> dict[str, Any]:
        config = _get_attr_or_key(node, "config") or {}
        profile_name = _require_str(config, "memory_profile")
        self._profile_resolver.resolve_memory_profile(spec, profile_name)

        scope = MemoryScope(_require_str(config, "scope"))
        query_config = _get_attr_or_key(config, "query") or {}
        tags = _ensure_string_list(_get_attr_or_key(query_config, "tags") or [])
        limit = int(_get_attr_or_key(query_config, "limit") or 5)

        query = MemoryQuery(
            scope=scope,
            workflow_id=_context_workflow_id_for_scope(scope, context),
            execution_id=_context_execution_id_for_scope(scope, context),
            tags=tags,
            limit=limit,
        )
        store = self._resolve_store(profile_name)
        return {
            "store": store,
            "query": query,
            "scope": scope,
            "profile_name": profile_name,
            "tags": tags,
        }

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> dict[str, Any]:
        store: MemoryStore = prepared_input["store"]
        query: MemoryQuery = prepared_input["query"]
        records = store.read(query)
        return {
            "records": [record.model_dump(mode="json") for record in records],
            "count": len(records),
            "scope": query.scope.value if query.scope is not None else None,
            "tags": list(query.tags),
        }

    def summarize_output(self, output: dict[str, Any]) -> str | None:
        return f"memory_read: {output.get('count', 0)} record(s)"

    def _resolve_store(self, profile_name: str) -> MemoryStore:
        if profile_name not in self._stores_by_profile_name:
            raise ValueError(
                f"memory_profile '{profile_name}' に対応する MemoryStore が登録されていません。"
            )
        return self._stores_by_profile_name[profile_name]


class MemoryWriteExecutor(BaseNodeExecutor):
    node_type = "memory_write"

    def __init__(
        self,
        *,
        stores_by_profile_name: Mapping[str, MemoryStore] | None = None,
        profile_resolver: ProfileResolver | None = None,
    ) -> None:
        self._stores_by_profile_name = dict(stores_by_profile_name or {})
        self._profile_resolver = profile_resolver or ProfileResolver()

    def prepare_input(self, *, spec: Any, node: Any, context: Any | None = None) -> dict[str, Any]:
        from agent_platform.integrations.memory_contracts import MemoryWriteRequest

        config = _get_attr_or_key(node, "config") or {}
        profile_name = _require_str(config, "memory_profile")
        self._profile_resolver.resolve_memory_profile(spec, profile_name)

        scope = MemoryScope(_require_str(config, "scope"))
        tags = _ensure_string_list(_get_attr_or_key(config, "tags") or [])
        mode = str(_get_attr_or_key(config, "mode") or "append")
        content = _build_content(node=node, context=context, config=config)

        request = MemoryWriteRequest(
            scope=scope,
            workflow_id=_context_workflow_id_for_scope(scope, context),
            execution_id=_context_execution_id_for_scope(scope, context),
            tags=tags,
            content=content,
        )
        store = self._resolve_store(profile_name)
        return {
            "store": store,
            "request": request,
            "scope": scope,
            "mode": mode,
            "tags": tags,
        }

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> dict[str, Any]:
        store: MemoryStore = prepared_input["store"]
        request = prepared_input["request"]
        record = store.write(request)
        return {
            "record_id": record.record_id,
            "scope": record.scope.value,
            "tags": list(record.tags),
            "mode": prepared_input["mode"],
        }

    def summarize_output(self, output: dict[str, Any]) -> str | None:
        record_id = output.get("record_id")
        if record_id:
            return f"memory_write: {record_id}"
        return "memory_write"

    def _resolve_store(self, profile_name: str) -> MemoryStore:
        if profile_name not in self._stores_by_profile_name:
            raise ValueError(
                f"memory_profile '{profile_name}' に対応する MemoryStore が登録されていません。"
            )
        return self._stores_by_profile_name[profile_name]


def _build_content(*, node: Any, context: Any | None, config: Any) -> dict[str, Any]:
    template = _get_attr_or_key(config, "content_template")
    if isinstance(template, Mapping):
        return dict(template)
    return {
        "node_id": _get_attr_or_key(node, "id"),
        "node_type": _get_attr_or_key(node, "type"),
        "context": _snapshot_context(context),
    }


def _snapshot_context(context: Any | None) -> dict[str, Any]:
    if context is None:
        return {}
    if isinstance(context, Mapping):
        return dict(context)
    return {
        "workflow_id": getattr(context, "workflow_id", None),
        "execution_id": getattr(context, "execution_id", None),
        "node_outputs": getattr(context, "node_outputs", None),
    }


def _context_workflow_id_for_scope(scope: MemoryScope, context: Any | None) -> str | None:
    if scope in {MemoryScope.EXECUTION, MemoryScope.WORKFLOW}:
        return _get_attr_or_key(context, "workflow_id")
    return None


def _context_execution_id_for_scope(scope: MemoryScope, context: Any | None) -> str | None:
    if scope == MemoryScope.EXECUTION:
        return _get_attr_or_key(context, "execution_id")
    return None


def _require_str(config: Any, field_name: str) -> str:
    value = _get_attr_or_key(config, field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"config.{field_name} が指定されていません。")
    return value


def _ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tags は list[str] である必要があります。")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("tags は list[str] である必要があります。")
        items.append(item)
    return items


def _get_attr_or_key(obj: Any, field_name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(field_name)
    return getattr(obj, field_name, None)
