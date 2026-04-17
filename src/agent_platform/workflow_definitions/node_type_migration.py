from __future__ import annotations

from copy import deepcopy
from typing import Any


LEGACY_NODE_TYPE_MAP: dict[str, str] = {
    "llm_generate": "llm",
    "llm_review": "llm",
    "memory_read": "llm",
    "memory_write": "llm",
    "rag_retrieve": "llm",
    "deterministic_transform": "llm",
    "tool_invoke": "api",
    "file_read": "api",
    "file_write": "api",
}


def normalize_workflow_node_types(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = deepcopy(data)
    warnings: list[str] = []

    nodes = normalized.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                _normalize_node_payload(node, warnings)
    elif isinstance(nodes, dict):
        for payload in nodes.values():
            if isinstance(payload, dict):
                _normalize_node_payload(payload, warnings)

    return normalized, warnings


def _normalize_node_payload(node: dict[str, Any], warnings: list[str]) -> None:
    type_key = "type" if "type" in node or "node_type" not in node else "node_type"
    raw_type = str(node.get(type_key) or "").strip().lower()
    if not raw_type:
        return

    normalized_type = LEGACY_NODE_TYPE_MAP.get(raw_type, raw_type)
    node[type_key] = normalized_type

    config = node.get("config")
    if not isinstance(config, dict):
        config = {}
    node["config"] = config

    node_id = str(node.get("id") or node.get("node_id") or "<unknown>")
    if raw_type == normalized_type:
        return

    warnings.append(
        f"node '{node_id}': legacy node type '{raw_type}' was migrated to '{normalized_type}'."
    )

    if raw_type in {"llm_generate", "llm_review"}:
        config.setdefault("task", "review" if raw_type == "llm_review" else "generate")
        return

    if raw_type == "rag_retrieve":
        rag = config.get("rag") if isinstance(config.get("rag"), dict) else {}
        rag.setdefault("profile", config.pop("rag_profile", None))
        rag.setdefault("top_k", config.get("top_k", 5))
        query_text = config.pop("query_text", None)
        query_source = config.pop("query_source", None)
        if query_text:
            rag.setdefault("query", query_text)
        elif query_source:
            rag.setdefault("query", query_source)
        config["rag"] = rag
        config.setdefault("task", "generate")
        return

    if raw_type == "memory_read":
        memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        read_cfg = memory.get("read") if isinstance(memory.get("read"), dict) else {}
        query_cfg = config.get("query") if isinstance(config.get("query"), dict) else {}
        read_cfg.setdefault("profile", config.pop("memory_profile", None))
        read_cfg.setdefault("scope", config.get("scope", "workflow"))
        read_cfg.setdefault("tags", query_cfg.get("tags", []))
        read_cfg.setdefault("limit", query_cfg.get("limit", 5))
        memory["read"] = read_cfg
        config["memory"] = memory
        config.setdefault("task", "generate")
        return

    if raw_type == "memory_write":
        memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        write_cfg = memory.get("write") if isinstance(memory.get("write"), dict) else {}
        write_cfg.setdefault("enabled", True)
        write_cfg.setdefault("profile", config.pop("memory_profile", None))
        write_cfg.setdefault("scope", config.get("scope", "workflow"))
        write_cfg.setdefault("tags", config.get("tags", []))
        if "content_template" in config:
            write_cfg.setdefault("content_template", config.get("content_template"))
        memory["write"] = write_cfg
        config["memory"] = memory
        config.setdefault("task", "generate")
        return

    if raw_type == "deterministic_transform":
        config.setdefault("task", "transform")
        transform = config.get("transform") if isinstance(config.get("transform"), dict) else {}
        if "transform_type" in config:
            transform.setdefault("type", config.get("transform_type"))
        if "params" in config:
            transform.setdefault("params", config.get("params"))
        if transform:
            config["transform"] = transform
        return

    if raw_type in {"tool_invoke", "file_read", "file_write"}:
        operation = {
            "tool_invoke": "invoke_tool",
            "file_read": "file_read",
            "file_write": "file_write",
        }[raw_type]
        config.setdefault("operation", operation)
