from __future__ import annotations

from collections import Counter

import networkx as nx

from agent_platform.models import IssueSeverity, NodeType, ValidationIssue, WorkflowSpec

from .adapter_validator import validate_profile_contracts

SUPPORTED_SCHEMA_VERSION = "0.1"
SUPPORTED_LLM_TASKS = {"generate", "assessment", "extract"}
SUPPORTED_EXTRACT_OUTPUT_FORMATS = {"json", "yaml", "markdown", "plain_text"}


def validate_workflow_spec(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    node_ids = [node.id for node in spec.nodes]
    node_id_set = set(node_ids)
    node_index_by_id: dict[str, int] = {}
    first_node_by_id: dict[str, object] = {}
    for index, node in enumerate(spec.nodes):
        node_index_by_id.setdefault(node.id, index)
        first_node_by_id.setdefault(node.id, node)

    issues.extend(_validate_schema_version(spec))
    issues.extend(_validate_runtime_nodes(spec, node_id_set))
    issues.extend(_validate_unique_node_ids(spec))
    issues.extend(_validate_node_basics(spec))
    issues.extend(_validate_edges(spec, node_id_set))
    issues.extend(_validate_reachability(spec, node_id_set))
    issues.extend(_validate_node_inputs(spec, node_id_set, first_node_by_id))
    issues.extend(_validate_node_configs(spec))
    issues.extend(validate_profile_contracts(spec))

    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity is IssueSeverity.ERROR for issue in issues)


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


def _validate_schema_version(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not spec.schema_version or not spec.schema_version.strip():
        issues.append(
            _issue(
                code="invalid_schema_version",
                message="schema_version must not be empty.",
                severity=IssueSeverity.ERROR,
                location="schema_version",
            )
        )
    elif spec.schema_version != SUPPORTED_SCHEMA_VERSION:
        issues.append(
            _issue(
                code="unsupported_schema_version",
                message=(
                    f"schema_version '{spec.schema_version}' is not the MVP default. "
                    f"Expected '{SUPPORTED_SCHEMA_VERSION}'."
                ),
                severity=IssueSeverity.WARNING,
                location="schema_version",
            )
        )

    if not spec.workflow.id or not spec.workflow.id.strip():
        issues.append(
            _issue(
                code="invalid_workflow_id",
                message="workflow.id must not be empty.",
                severity=IssueSeverity.ERROR,
                location="workflow.id",
            )
        )
    return issues


def _validate_runtime_nodes(spec: WorkflowSpec, node_id_set: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if spec.runtime.start_node not in node_id_set:
        issues.append(
            _issue(
                code="missing_start_node_ref",
                message=f"runtime.start_node '{spec.runtime.start_node}' does not exist in nodes.",
                severity=IssueSeverity.ERROR,
                location="runtime.start_node",
            )
        )

    for index, end_node in enumerate(spec.runtime.end_nodes):
        if end_node not in node_id_set:
            issues.append(
                _issue(
                    code="missing_end_node_ref",
                    message=f"runtime.end_nodes[{index}] '{end_node}' does not exist in nodes.",
                    severity=IssueSeverity.ERROR,
                    location=f"runtime.end_nodes[{index}]",
                )
            )
    return issues


def _validate_unique_node_ids(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    counts = Counter(node.id for node in spec.nodes)
    for node_id, count in counts.items():
        if count > 1:
            issues.append(
                _issue(
                    code="duplicate_node_id",
                    message=f"Node id '{node_id}' is duplicated {count} times.",
                    severity=IssueSeverity.ERROR,
                    related_node_id=node_id,
                    location="nodes",
                )
            )
    return issues


def _validate_node_basics(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, node in enumerate(spec.nodes):
        if not node.name.strip():
            issues.append(
                _issue(
                    code="empty_node_name",
                    message=f"Node '{node.id}' has an empty name.",
                    severity=IssueSeverity.WARNING,
                    location=f"nodes[{index}].name",
                    related_node_id=node.id,
                )
            )
        if node.retry is not None and node.retry.max_attempts < 1:
            issues.append(
                _issue(
                    code="invalid_retry_value",
                    message=f"Node '{node.id}' has retry.max_attempts < 1.",
                    severity=IssueSeverity.ERROR,
                    location=f"nodes[{index}].retry.max_attempts",
                    related_node_id=node.id,
                )
            )
    return issues


def _validate_edges(spec: WorkflowSpec, node_id_set: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, edge in enumerate(spec.edges):
        if edge.from_node not in node_id_set:
            issues.append(
                _issue(
                    code="invalid_edge_ref",
                    message=f"Edge source '{edge.from_node}' does not exist.",
                    severity=IssueSeverity.ERROR,
                    location=f"edges[{index}].from",
                    related_node_id=edge.from_node,
                )
            )
        if edge.to_node not in node_id_set:
            issues.append(
                _issue(
                    code="invalid_edge_ref",
                    message=f"Edge target '{edge.to_node}' does not exist.",
                    severity=IssueSeverity.ERROR,
                    location=f"edges[{index}].to",
                    related_node_id=edge.to_node,
                )
            )
        if edge.from_node == edge.to_node:
            issues.append(
                _issue(
                    code="self_loop_edge",
                    message=f"Edge '{edge.from_node}' -> '{edge.to_node}' is a self loop.",
                    severity=IssueSeverity.WARNING,
                    location=f"edges[{index}]",
                    related_node_id=edge.from_node,
                )
            )
    return issues


def _validate_reachability(spec: WorkflowSpec, node_id_set: set[str]) -> list[ValidationIssue]:
    if spec.runtime.start_node not in node_id_set:
        return []

    graph = nx.DiGraph()
    graph.add_nodes_from(node_id_set)
    for edge in spec.edges:
        if edge.from_node in node_id_set and edge.to_node in node_id_set:
            graph.add_edge(edge.from_node, edge.to_node)

    reachable = nx.descendants(graph, spec.runtime.start_node) | {spec.runtime.start_node}
    issues: list[ValidationIssue] = []

    for node_id in sorted(node_id_set - reachable):
        severity = IssueSeverity.ERROR if node_id in spec.runtime.end_nodes else IssueSeverity.WARNING
        code = "unreachable_end_node" if node_id in spec.runtime.end_nodes else "unreachable_node"
        message = (
            f"End node '{node_id}' is unreachable from start node '{spec.runtime.start_node}'."
            if node_id in spec.runtime.end_nodes
            else f"Node '{node_id}' is unreachable from start node '{spec.runtime.start_node}'."
        )
        issues.append(
            _issue(
                code=code,
                message=message,
                severity=severity,
                location="runtime.end_nodes" if node_id in spec.runtime.end_nodes else "nodes",
                related_node_id=node_id,
            )
        )

    if spec.runtime.end_nodes and not any(end_node in reachable for end_node in spec.runtime.end_nodes):
        issues.append(
            _issue(
                code="unreachable_end_node",
                message="No end node is reachable from the start node.",
                severity=IssueSeverity.ERROR,
                location="runtime.end_nodes",
            )
        )

    return issues


def _validate_node_inputs(spec: WorkflowSpec, node_id_set: set[str], node_by_id: dict[str, object]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for node_index, node in enumerate(spec.nodes):
        if node.input is None:
            continue
        for source_index, source in enumerate(node.input.from_):
            if source.node not in node_id_set:
                issues.append(
                    _issue(
                        code="invalid_input_ref",
                        message=f"Node '{node.id}' input references unknown node '{source.node}'.",
                        severity=IssueSeverity.ERROR,
                        location=f"nodes[{node_index}].input.from[{source_index}].node",
                        related_node_id=node.id,
                    )
                )
                continue

            source_node = node_by_id[source.node]
            source_output = getattr(source_node, "output", None)
            source_output_key = getattr(source_output, "key", None) if source_output is not None else None
            if not source_output_key:
                issues.append(
                    _issue(
                        code="missing_output_key_on_source",
                        message=(
                            f"Node '{node.id}' references '{source.node}.{source.key}', but the source node "
                            "does not define output.key."
                        ),
                        severity=IssueSeverity.WARNING,
                        location=f"nodes[{node_index}].input.from[{source_index}].key",
                        related_node_id=node.id,
                    )
                )
            elif source.key != source_output_key:
                issues.append(
                    _issue(
                        code="mismatched_output_key_ref",
                        message=(
                            f"Node '{node.id}' references key '{source.key}', but source node '{source.node}' "
                            f"declares output.key '{source_output_key}'."
                        ),
                        severity=IssueSeverity.WARNING,
                        location=f"nodes[{node_index}].input.from[{source_index}].key",
                        related_node_id=node.id,
                    )
                )
    return issues


def _validate_node_configs(spec: WorkflowSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    llm_profiles = spec.integrations.llm_profiles
    memory_profiles = spec.integrations.memory_profiles
    rag_profiles = spec.integrations.rag_profiles
    tool_profiles = spec.integrations.tool_profiles

    for index, node in enumerate(spec.nodes):
        location_prefix = f"nodes[{index}].config"
        if node.type is NodeType.LLM:
            llm_profile = node.config.get("llm_profile")
            if not isinstance(llm_profile, str) or not llm_profile:
                issues.append(
                    _issue(
                        code="missing_required_profile",
                        message=f"Node '{node.id}' requires config.llm_profile.",
                        severity=IssueSeverity.ERROR,
                        location=f"{location_prefix}.llm_profile",
                        related_node_id=node.id,
                    )
                )
            elif llm_profile not in llm_profiles:
                issues.append(
                    _issue(
                        code="unknown_profile_ref",
                        message=f"Node '{node.id}' references unknown llm_profile '{llm_profile}'.",
                        severity=IssueSeverity.ERROR,
                        location=f"{location_prefix}.llm_profile",
                        related_node_id=node.id,
                    )
                )
            task = node.config.get("task")
            if task is not None and (not isinstance(task, str) or task not in SUPPORTED_LLM_TASKS):
                issues.append(
                    _issue(
                        code="invalid_llm_task",
                        message=f"Node '{node.id}' has invalid config.task '{task}'.",
                        severity=IssueSeverity.WARNING,
                        location=f"{location_prefix}.task",
                        related_node_id=node.id,
                    )
                )
            normalized_task = task if isinstance(task, str) else "generate"

            temperature = node.config.get("temperature")
            if temperature is not None:
                try:
                    float(temperature)
                except (TypeError, ValueError):
                    issues.append(
                        _issue(
                            code="invalid_temperature",
                            message=f"Node '{node.id}' config.temperature must be numeric.",
                            severity=IssueSeverity.WARNING,
                            location=f"{location_prefix}.temperature",
                            related_node_id=node.id,
                        )
                    )

            if normalized_task == "assessment":
                options = node.config.get("assessment_options")
                if options is not None and not isinstance(options, list):
                    issues.append(
                        _issue(
                            code="invalid_assessment_options",
                            message=f"Node '{node.id}' config.assessment_options must be an array.",
                            severity=IssueSeverity.WARNING,
                            location=f"{location_prefix}.assessment_options",
                            related_node_id=node.id,
                        )
                    )
                routes = node.config.get("assessment_routes")
                if routes is not None:
                    if not isinstance(routes, dict):
                        issues.append(
                            _issue(
                                code="invalid_assessment_routes",
                                message=f"Node '{node.id}' config.assessment_routes must be an object.",
                                severity=IssueSeverity.ERROR,
                                location=f"{location_prefix}.assessment_routes",
                                related_node_id=node.id,
                            )
                        )
                    else:
                        for option, target_node_id in routes.items():
                            if not isinstance(option, str) or not option.strip():
                                issues.append(
                                    _issue(
                                        code="invalid_assessment_routes",
                                        message=f"Node '{node.id}' has empty option key in config.assessment_routes.",
                                        severity=IssueSeverity.ERROR,
                                        location=f"{location_prefix}.assessment_routes",
                                        related_node_id=node.id,
                                    )
                                )
                                continue
                            if not isinstance(target_node_id, str) or not target_node_id.strip():
                                issues.append(
                                    _issue(
                                        code="invalid_assessment_routes",
                                        message=f"Node '{node.id}' route '{option}' must map to non-empty node id.",
                                        severity=IssueSeverity.ERROR,
                                        location=f"{location_prefix}.assessment_routes.{option}",
                                        related_node_id=node.id,
                                    )
                                )
                                continue
                            if not any(candidate.id == target_node_id for candidate in spec.nodes):
                                issues.append(
                                    _issue(
                                        code="invalid_assessment_route_ref",
                                        message=f"Node '{node.id}' route '{option}' references unknown node '{target_node_id}'.",
                                        severity=IssueSeverity.ERROR,
                                        location=f"{location_prefix}.assessment_routes.{option}",
                                        related_node_id=node.id,
                                    )
                                )

            if normalized_task == "extract":
                extract_fields = node.config.get("extract_fields")
                if extract_fields is not None and not isinstance(extract_fields, list):
                    issues.append(
                        _issue(
                            code="invalid_extract_fields",
                            message=f"Node '{node.id}' config.extract_fields must be an array.",
                            severity=IssueSeverity.WARNING,
                            location=f"{location_prefix}.extract_fields",
                            related_node_id=node.id,
                        )
                    )
                extract_output_format = node.config.get("extract_output_format")
                if extract_output_format is not None and (
                    not isinstance(extract_output_format, str)
                    or extract_output_format not in SUPPORTED_EXTRACT_OUTPUT_FORMATS
                ):
                    issues.append(
                        _issue(
                            code="invalid_extract_output_format",
                            message=(
                                f"Node '{node.id}' has invalid config.extract_output_format "
                                f"'{extract_output_format}'."
                            ),
                            severity=IssueSeverity.WARNING,
                            location=f"{location_prefix}.extract_output_format",
                            related_node_id=node.id,
                        )
                    )

            memory = node.config.get("memory")
            if memory is not None and not isinstance(memory, dict):
                issues.append(
                    _issue(
                        code="invalid_memory_config",
                        message=f"Node '{node.id}' config.memory must be an object.",
                        severity=IssueSeverity.ERROR,
                        location=f"{location_prefix}.memory",
                        related_node_id=node.id,
                    )
                )
            elif isinstance(memory, dict):
                for key in ("read", "write"):
                    cfg = memory.get(key)
                    if cfg is None:
                        continue
                    if not isinstance(cfg, dict):
                        issues.append(
                            _issue(
                                code="invalid_memory_config",
                                message=f"Node '{node.id}' config.memory.{key} must be an object.",
                                severity=IssueSeverity.ERROR,
                                location=f"{location_prefix}.memory.{key}",
                                related_node_id=node.id,
                            )
                        )
                        continue
                    profile_name = cfg.get("profile")
                    if profile_name is not None:
                        if not isinstance(profile_name, str) or not profile_name:
                            issues.append(
                                _issue(
                                    code="missing_required_profile",
                                    message=f"Node '{node.id}' config.memory.{key}.profile must be non-empty string.",
                                    severity=IssueSeverity.ERROR,
                                    location=f"{location_prefix}.memory.{key}.profile",
                                    related_node_id=node.id,
                                )
                            )
                        elif profile_name not in memory_profiles:
                            issues.append(
                                _issue(
                                    code="unknown_profile_ref",
                                    message=f"Node '{node.id}' references unknown memory_profile '{profile_name}'.",
                                    severity=IssueSeverity.ERROR,
                                    location=f"{location_prefix}.memory.{key}.profile",
                                    related_node_id=node.id,
                                )
                            )

            rag = node.config.get("rag")
            if rag is not None and not isinstance(rag, dict):
                issues.append(
                    _issue(
                        code="invalid_rag_config",
                        message=f"Node '{node.id}' config.rag must be an object.",
                        severity=IssueSeverity.ERROR,
                        location=f"{location_prefix}.rag",
                        related_node_id=node.id,
                    )
                )
            elif isinstance(rag, dict):
                rag_profile = rag.get("profile")
                if rag_profile is not None:
                    if not isinstance(rag_profile, str) or not rag_profile:
                        issues.append(
                            _issue(
                                code="missing_required_profile",
                                message=f"Node '{node.id}' config.rag.profile must be non-empty string.",
                                severity=IssueSeverity.ERROR,
                                location=f"{location_prefix}.rag.profile",
                                related_node_id=node.id,
                            )
                        )
                    elif rag_profile not in rag_profiles:
                        issues.append(
                            _issue(
                                code="unknown_profile_ref",
                                message=f"Node '{node.id}' references unknown rag_profile '{rag_profile}'.",
                                severity=IssueSeverity.ERROR,
                                location=f"{location_prefix}.rag.profile",
                                related_node_id=node.id,
                            )
                        )

        elif node.type is NodeType.HUMAN_GATE:
            gate_type = node.config.get("gate_type")
            if gate_type is not None and gate_type not in {"approval", "review"}:
                issues.append(
                    _issue(
                        code="invalid_gate_type",
                        message=f"Node '{node.id}' has invalid gate_type '{gate_type}'.",
                        severity=IssueSeverity.ERROR,
                        location=f"{location_prefix}.gate_type",
                        related_node_id=node.id,
                    )
                )
            on_reject = node.config.get("on_reject")
            if on_reject is not None:
                if not isinstance(on_reject, str) or not any(candidate.id == on_reject for candidate in spec.nodes):
                    issues.append(
                        _issue(
                            code="invalid_on_reject_ref",
                            message=f"Node '{node.id}' references invalid on_reject '{on_reject}'.",
                            severity=IssueSeverity.ERROR,
                            location=f"{location_prefix}.on_reject",
                            related_node_id=node.id,
                        )
                    )

        elif node.type in {NodeType.API, NodeType.MCP}:
            tool_profile = node.config.get("tool_profile")
            if tool_profile is None:
                issues.append(
                    _issue(
                        code="missing_recommended_profile",
                        message=f"Node '{node.id}' does not declare config.tool_profile.",
                        severity=IssueSeverity.WARNING,
                        location=f"{location_prefix}.tool_profile",
                        related_node_id=node.id,
                    )
                )
            elif isinstance(tool_profile, str) and tool_profile and tool_profile not in tool_profiles:
                issues.append(
                    _issue(
                        code="unknown_profile_ref",
                        message=f"Node '{node.id}' references unknown tool_profile '{tool_profile}'.",
                        severity=IssueSeverity.WARNING,
                        location=f"{location_prefix}.tool_profile",
                        related_node_id=node.id,
                    )
                )

    return issues
