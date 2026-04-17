from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent_platform.models import ContractType, IssueSeverity, NodeType, ValidationIssue, WorkflowSpec

LLM_CAPABILITIES = {"chat", "json_output", "tool_call", "embedding_delegate"}
MEMORY_CAPABILITIES = {"read", "write", "tag_filter", "scope_filter"}
RAG_CAPABILITIES = {"search", "metadata_filter", "score_return"}
TOOL_CAPABILITIES = {"invoke_tool", "list_tools", "structured_result"}
FILE_CAPABILITIES = {"read", "write", "list_files", "metadata_read"}


def validate_profile_contracts(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    issues.extend(_validate_llm_profiles(spec))
    issues.extend(_validate_memory_profiles(spec))
    issues.extend(_validate_rag_profiles(spec))
    issues.extend(_validate_tool_profiles(spec))
    issues.extend(_validate_required_capabilities(spec))

    return issues


def _issue(
    *,
    code: str,
    message: str,
    severity: IssueSeverity,
    location: str | None = None,
    related_node_id: str | None = None,
    suggestion: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity=severity,
        location=location,
        related_node_id=related_node_id,
        suggestion=suggestion,
    )


def _validate_llm_profiles(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, profile in spec.integrations.llm_profiles.items():
        location = f"integrations.llm_profiles.{name}"
        if profile.contract is not None and profile.contract is not ContractType.LLM_COMPLETION:
            issues.append(
                _issue(
                    code="invalid_contract_type",
                    message=f"LLM profile '{name}' must use contract 'llm_completion'.",
                    severity=IssueSeverity.ERROR,
                    location=f"{location}.contract",
                )
            )
        issues.extend(_validate_capabilities(profile.capabilities, LLM_CAPABILITIES, location))
        issues.extend(_validate_connection_ref(profile.adapter_ref, profile.connection_ref, location))
    return issues


def _validate_memory_profiles(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, profile in spec.integrations.memory_profiles.items():
        location = f"integrations.memory_profiles.{name}"
        if profile.contract is not None and profile.contract is not ContractType.MEMORY_STORE:
            issues.append(
                _issue(
                    code="invalid_contract_type",
                    message=f"Memory profile '{name}' must use contract 'memory_store'.",
                    severity=IssueSeverity.ERROR,
                    location=f"{location}.contract",
                )
            )
        issues.extend(_validate_capabilities(profile.capabilities, MEMORY_CAPABILITIES, location))
        issues.extend(_validate_connection_ref(profile.adapter_ref, profile.connection_ref, location))
    return issues


def _validate_rag_profiles(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, profile in spec.integrations.rag_profiles.items():
        location = f"integrations.rag_profiles.{name}"
        if profile.contract is not None and profile.contract is not ContractType.VECTOR_RETRIEVER:
            issues.append(
                _issue(
                    code="invalid_contract_type",
                    message=f"RAG profile '{name}' must use contract 'vector_retriever'.",
                    severity=IssueSeverity.ERROR,
                    location=f"{location}.contract",
                )
            )
        issues.extend(_validate_capabilities(profile.capabilities, RAG_CAPABILITIES, location))
        issues.extend(_validate_connection_ref(profile.adapter_ref, profile.connection_ref, location))
    return issues


def _validate_tool_profiles(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, profile in spec.integrations.tool_profiles.items():
        location = f"integrations.tool_profiles.{name}"
        allowed_contracts = {ContractType.TOOL_INVOCATION, ContractType.FILE_ACCESS}
        if profile.contract is not None and profile.contract not in allowed_contracts:
            issues.append(
                _issue(
                    code="invalid_contract_type",
                    message=f"Tool profile '{name}' must use contract 'tool_invocation' or 'file_access'.",
                    severity=IssueSeverity.ERROR,
                    location=f"{location}.contract",
                )
            )

        if profile.contract is ContractType.FILE_ACCESS:
            allowed_capabilities = FILE_CAPABILITIES
        elif profile.contract is ContractType.TOOL_INVOCATION:
            allowed_capabilities = TOOL_CAPABILITIES
        else:
            allowed_capabilities = TOOL_CAPABILITIES | FILE_CAPABILITIES

        issues.extend(_validate_capabilities(profile.capabilities, allowed_capabilities, location))
        issues.extend(_validate_connection_ref(profile.adapter_ref, profile.connection_ref, location))
    return issues


def _validate_required_capabilities(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for index, node in enumerate(spec.nodes):
        required = _normalize_required_capabilities(node.config.get("required_capabilities"))
        if not required:
            continue

        profile_name: str | None = None
        profile_capabilities: set[str] | None = None
        profile_location: str | None = None

        if node.type is NodeType.LLM:
            profile_name = _as_optional_str(node.config.get("llm_profile"))
            if profile_name and profile_name in spec.integrations.llm_profiles:
                profile_capabilities = set(spec.integrations.llm_profiles[profile_name].capabilities)
                profile_location = f"integrations.llm_profiles.{profile_name}"
            memory = node.config.get("memory")
            if isinstance(memory, dict):
                for key in ("read", "write"):
                    cfg = memory.get(key)
                    if not isinstance(cfg, dict):
                        continue
                    memory_profile = _as_optional_str(cfg.get("profile"))
                    if memory_profile and memory_profile in spec.integrations.memory_profiles:
                        profile_capabilities = set(spec.integrations.memory_profiles[memory_profile].capabilities)
                        profile_location = f"integrations.memory_profiles.{memory_profile}"
            rag = node.config.get("rag")
            if isinstance(rag, dict):
                rag_profile = _as_optional_str(rag.get("profile"))
                if rag_profile and rag_profile in spec.integrations.rag_profiles:
                    profile_capabilities = set(spec.integrations.rag_profiles[rag_profile].capabilities)
                    profile_location = f"integrations.rag_profiles.{rag_profile}"
        elif node.type in {NodeType.API, NodeType.MCP}:
            profile_name = _as_optional_str(node.config.get("tool_profile"))
            if profile_name and profile_name in spec.integrations.tool_profiles:
                profile_capabilities = set(spec.integrations.tool_profiles[profile_name].capabilities)
                profile_location = f"integrations.tool_profiles.{profile_name}"

        if profile_capabilities is None or profile_location is None:
            continue

        for capability in required:
            if capability not in profile_capabilities:
                issues.append(
                    _issue(
                        code="missing_required_capability",
                        message=(
                            f"Node '{node.id}' requires capability '{capability}', but profile '{profile_name}' "
                            "does not declare it."
                        ),
                        severity=IssueSeverity.WARNING,
                        location=f"nodes[{index}].config.required_capabilities",
                        related_node_id=node.id,
                        suggestion=f"Add '{capability}' to {profile_location}.capabilities or change the node config.",
                    )
                )

    return issues


def _validate_capabilities(
    capabilities: list[str],
    allowed_capabilities: set[str],
    location_prefix: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for capability in capabilities:
        if capability not in allowed_capabilities:
            issues.append(
                _issue(
                    code="unknown_capability",
                    message=f"Unknown capability '{capability}'.",
                    severity=IssueSeverity.WARNING,
                    location=f"{location_prefix}.capabilities",
                )
            )
    return issues


def _validate_connection_ref(
    adapter_ref: str | None,
    connection_ref: str | None,
    location_prefix: str,
) -> list[ValidationIssue]:
    if adapter_ref and not connection_ref:
        return [
            _issue(
                code="missing_connection_ref",
                message="adapter_ref is set but connection_ref is missing.",
                severity=IssueSeverity.WARNING,
                location=f"{location_prefix}.connection_ref",
            )
        ]
    return []


def _normalize_required_capabilities(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [item for item in value if isinstance(item, str)]
    return []


def _as_optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
