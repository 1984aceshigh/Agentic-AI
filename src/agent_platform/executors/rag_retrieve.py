from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor
from agent_platform.integrations.profile_resolver import ProfileResolver
from agent_platform.integrations.rag_contracts import RetrievalQuery, VectorRetriever


class RAGRetrieveExecutor(BaseNodeExecutor):
    node_type = "rag_retrieve"

    def __init__(
        self,
        *,
        retrievers_by_profile_name: Mapping[str, VectorRetriever] | None = None,
        profile_resolver: ProfileResolver | Any | None = None,
    ) -> None:
        self._retrievers_by_profile_name = dict(retrievers_by_profile_name or {})
        self._profile_resolver = profile_resolver or ProfileResolver()

    def prepare_input(self, *, spec: Any, node: Any, context: Any | None = None) -> dict[str, Any]:
        config = self._get_attr_or_key(node, "config") or {}
        profile_name = _require_str(config, "rag_profile")
        self._profile_resolver.resolve_rag_profile(spec, profile_name)

        query_text = _resolve_query_text(
            config=config,
            context=context,
            resolved_inputs=super().prepare_input(spec=spec, node=node, context=context),
        )
        if not query_text.strip():
            raise ValueError("query_text が空です。")

        top_k = int(self._get_attr_or_key(config, "top_k") or 5)
        filters = self._get_attr_or_key(config, "filters") or {}
        if not isinstance(filters, dict):
            raise ValueError("config.filters は dict である必要があります。")

        query = RetrievalQuery(
            query_text=query_text,
            top_k=top_k,
            filters=dict(filters),
        )
        retriever = self._resolve_retriever(profile_name)
        return {
            "retriever": retriever,
            "query": query,
            "profile_name": profile_name,
        }

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> dict[str, Any]:
        retriever: VectorRetriever = prepared_input["retriever"]
        query: RetrievalQuery = prepared_input["query"]
        hits = retriever.retrieve(query)
        return {
            "hits": [hit.model_dump(mode="json") for hit in hits],
            "count": len(hits),
            "query_text": query.query_text,
        }

    def summarize_output(self, output: dict[str, Any]) -> str | None:
        return f"rag_retrieve: {output.get('count', 0)} hit(s)"

    def _resolve_retriever(self, profile_name: str) -> VectorRetriever:
        if profile_name not in self._retrievers_by_profile_name:
            raise ValueError(
                f"rag_profile '{profile_name}' に対応する VectorRetriever が登録されていません。"
            )
        return self._retrievers_by_profile_name[profile_name]



def _resolve_query_text(*, config: Any, context: Any | None, resolved_inputs: dict[str, Any]) -> str:
    direct_query_text = _get_attr_or_key(config, "query_text")
    if isinstance(direct_query_text, str) and direct_query_text.strip():
        return direct_query_text

    query_source = _get_attr_or_key(config, "query_source")
    if query_source is None:
        return ""

    resolved_input_values = resolved_inputs.get("resolved_inputs") or {}
    global_inputs = resolved_inputs.get("global_inputs") or {}

    if isinstance(query_source, str):
        value = resolved_input_values.get(query_source)
        if value is None:
            value = global_inputs.get(query_source)
        if value is None:
            return ""
        return str(value)

    if isinstance(query_source, Mapping):
        if isinstance(query_source.get("text"), str):
            return str(query_source["text"])
        if isinstance(query_source.get("resolved_input"), str):
            value = resolved_input_values.get(query_source["resolved_input"])
            return "" if value is None else str(value)
        if isinstance(query_source.get("global_input"), str):
            value = global_inputs.get(query_source["global_input"])
            return "" if value is None else str(value)
        node_output = query_source.get("node_output")
        if isinstance(node_output, str) and "." in node_output:
            node_id, key = node_output.split(".", 1)
            outputs = _get_attr_or_key(context, "node_outputs") or {}
            node_data = outputs.get(node_id) if isinstance(outputs, dict) else None
            if isinstance(node_data, dict):
                value = node_data.get(key)
                return "" if value is None else str(value)
        if isinstance(node_output, Mapping):
            node_id = node_output.get("node")
            key = node_output.get("key")
            outputs = _get_attr_or_key(context, "node_outputs") or {}
            node_data = outputs.get(node_id) if isinstance(outputs, dict) else None
            if isinstance(node_data, dict):
                value = node_data.get(key)
                return "" if value is None else str(value)

    return ""



def _require_str(config: Any, field_name: str) -> str:
    value = _get_attr_or_key(config, field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"config.{field_name} が指定されていません。")
    return value



def _get_attr_or_key(obj: Any, field_name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(field_name)
    return getattr(obj, field_name, None)
