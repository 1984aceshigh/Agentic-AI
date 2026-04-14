from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

try:
    from agent_platform.models.workflow import NodeSpec, WorkflowSpec
except Exception:  # pragma: no cover - keeps this module importable in isolation
    WorkflowSpec = Any  # type: ignore[misc,assignment]
    NodeSpec = Any  # type: ignore[misc,assignment]


LLM_NODE_TYPES: Final[set[str]] = {"llm_generate", "llm_review"}
MEMORY_NODE_TYPES: Final[set[str]] = {"memory_read", "memory_write"}
RAG_NODE_TYPES: Final[set[str]] = {"rag_retrieve"}
TOOL_NODE_TYPES: Final[set[str]] = {"tool_invoke"}
FILE_NODE_TYPES: Final[set[str]] = {"file_read", "file_write"}
TOOL_LIKE_NODE_TYPES: Final[set[str]] = TOOL_NODE_TYPES | FILE_NODE_TYPES


class ProfileResolutionError(ValueError):
    """Raised when a node-level integration profile cannot be resolved."""


class ProfileResolver:
    """Resolve integration profiles declared under ``spec.integrations``.

    This resolver is intentionally limited to logical profile resolution.
    It does not initialize adapters, resolve connection references, or perform
    external connectivity checks.
    """

    def resolve_llm_profile(self, spec: WorkflowSpec, profile_name: str) -> Any:
        profile = self._resolve_named_profile(
            spec=spec,
            container_name="llm_profiles",
            profile_name=profile_name,
        )
        self._validate_contract(
            profile=profile,
            expected_contracts={"llm_completion"},
            profile_kind="llm_profile",
            profile_name=profile_name,
        )
        return profile

    def resolve_memory_profile(self, spec: WorkflowSpec, profile_name: str) -> Any:
        profile = self._resolve_named_profile(
            spec=spec,
            container_name="memory_profiles",
            profile_name=profile_name,
        )
        self._validate_contract(
            profile=profile,
            expected_contracts={"memory_store"},
            profile_kind="memory_profile",
            profile_name=profile_name,
        )
        return profile

    def resolve_rag_profile(self, spec: WorkflowSpec, profile_name: str) -> Any:
        profile = self._resolve_named_profile(
            spec=spec,
            container_name="rag_profiles",
            profile_name=profile_name,
        )
        self._validate_contract(
            profile=profile,
            expected_contracts={"vector_retriever"},
            profile_kind="rag_profile",
            profile_name=profile_name,
        )
        return profile

    def resolve_tool_profile(self, spec: WorkflowSpec, profile_name: str) -> Any:
        return self._resolve_named_profile(
            spec=spec,
            container_name="tool_profiles",
            profile_name=profile_name,
        )

    def resolve_profile_for_node(self, spec: WorkflowSpec, node: NodeSpec) -> Any | None:
        node_type = self._node_type(node)
        config = self._node_config(node)

        if node_type in LLM_NODE_TYPES:
            profile_name = self._required_config_value(
                config=config,
                field_name="llm_profile",
                node=node,
            )
            return self.resolve_llm_profile(spec, profile_name)

        if node_type in MEMORY_NODE_TYPES:
            profile_name = self._required_config_value(
                config=config,
                field_name="memory_profile",
                node=node,
            )
            return self.resolve_memory_profile(spec, profile_name)

        if node_type in RAG_NODE_TYPES:
            profile_name = self._required_config_value(
                config=config,
                field_name="rag_profile",
                node=node,
            )
            return self.resolve_rag_profile(spec, profile_name)

        if node_type in TOOL_LIKE_NODE_TYPES:
            profile_name = self._required_config_value(
                config=config,
                field_name="tool_profile",
                node=node,
            )
            profile = self.resolve_tool_profile(spec, profile_name)
            expected_contracts = (
                {"tool_invocation"}
                if node_type in TOOL_NODE_TYPES
                else {"file_access"}
            )
            self._validate_contract(
                profile=profile,
                expected_contracts=expected_contracts,
                profile_kind="tool_profile",
                profile_name=profile_name,
                node=node,
            )
            return profile

        return None

    def _resolve_named_profile(
        self,
        *,
        spec: WorkflowSpec,
        container_name: str,
        profile_name: str,
    ) -> Any:
        integrations = self._get_attr_or_key(spec, "integrations")
        containers = self._get_attr_or_key(integrations, container_name)
        mapping = self._as_mapping(containers)

        if not profile_name:
            raise ProfileResolutionError(
                f"{container_name} の profile 名が空です。",
            )

        if profile_name not in mapping:
            raise ProfileResolutionError(
                f"{container_name} に '{profile_name}' が見つかりません。",
            )

        return mapping[profile_name]

    def _required_config_value(
        self,
        *,
        config: Any,
        field_name: str,
        node: NodeSpec,
    ) -> str:
        value = self._get_attr_or_key(config, field_name)
        if value in (None, ""):
            raise ProfileResolutionError(
                self._format_node_error(
                    node=node,
                    message=f"config.{field_name} が指定されていません。",
                ),
            )
        if not isinstance(value, str):
            raise ProfileResolutionError(
                self._format_node_error(
                    node=node,
                    message=f"config.{field_name} は文字列である必要があります。",
                ),
            )
        return value

    def _validate_contract(
        self,
        *,
        profile: Any,
        expected_contracts: set[str],
        profile_kind: str,
        profile_name: str,
        node: NodeSpec | None = None,
    ) -> None:
        actual_contract = self._get_attr_or_key(profile, "contract")
        if actual_contract in (None, ""):
            return
        if actual_contract not in expected_contracts:
            expected = ", ".join(sorted(expected_contracts))
            message = (
                f"{profile_kind} '{profile_name}' の contract が不正です。"
                f" expected={expected}, actual={actual_contract}"
            )
            if node is not None:
                message = self._format_node_error(node=node, message=message)
            raise ProfileResolutionError(message)

    def _node_type(self, node: NodeSpec) -> str:
        node_type = self._get_attr_or_key(node, "type")
        return str(node_type) if node_type is not None else ""

    def _node_config(self, node: NodeSpec) -> Any:
        return self._get_attr_or_key(node, "config")

    @staticmethod
    def _get_attr_or_key(obj: Any, field_name: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, Mapping):
            return obj.get(field_name)
        return getattr(obj, field_name, None)

    @staticmethod
    def _as_mapping(obj: Any) -> Mapping[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, Mapping):
            return obj
        items = getattr(obj, "items", None)
        if callable(items):
            return dict(items())
        raise ProfileResolutionError(
            "integration profiles は mapping 形式で保持されている必要があります。",
        )

    def _format_node_error(self, *, node: NodeSpec, message: str) -> str:
        node_id = self._get_attr_or_key(node, "id") or "<unknown>"
        node_type = self._get_attr_or_key(node, "type") or "<unknown>"
        return f"node_id={node_id}, node_type={node_type}: {message}"
