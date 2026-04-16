from __future__ import annotations

import json
import re
import textwrap
from collections.abc import Mapping
from typing import Any

from agent_platform.executors.base import BaseNodeExecutor, ExecutorResult
from agent_platform.integrations.llm_adapters import (
    DummyEchoLLMAdapter,
    LLMCompletionAdapter,
    LLMCompletionRequest,
)


class LLMReviewExecutor(BaseNodeExecutor):
    """LLM-backed executor for llm_review nodes."""

    node_type = "llm_review"

    def __init__(
        self,
        *,
        adapters_by_provider: Mapping[str, LLMCompletionAdapter] | None = None,
        default_adapter: LLMCompletionAdapter | None = None,
    ) -> None:
        self._adapters_by_provider = {
            str(provider): adapter for provider, adapter in (adapters_by_provider or {}).items()
        }
        self._default_adapter = default_adapter or DummyEchoLLMAdapter()

    def execute(self, context: Any, node: Any) -> ExecutorResult:
        try:
            prepared = self.prepare_input(context=context, node=node)
            node_id = getattr(node, "id", "unknown_node")

            config = prepared.get("node_config", {})
            prompt = str(config.get("prompt") or "").strip()
            if not prompt:
                prompt = f"reviewed by {node_id}"
            input_definition = self._resolve_input_definition(
                raw_input_definition=config.get("input_definition"),
                prepared=prepared,
            )
            output_format = self._optional_str(config.get("output_format"))
            prompt = self._build_prompt(
                prompt=prompt,
                input_definition=input_definition,
                resolved_inputs=prepared.get("resolved_inputs", {}),
                output_format=output_format,
            )

            adapter = self._resolve_adapter(config)
            response = adapter.complete(
                LLMCompletionRequest(
                    prompt=prompt,
                    system_prompt=self._optional_str(config.get("system_prompt")),
                    model=self._optional_str(config.get("model")),
                    temperature=self._optional_float(config.get("temperature")),
                    max_tokens=self._optional_int(config.get("max_tokens")),
                )
            )

            output: dict[str, Any] = {"review": response.text, "score": 80}
            structured = self._parse_structured_output(response.text, output_format)
            if structured is not None:
                output["structured_review"] = structured

            return ExecutorResult(
                status="SUCCEEDED",
                output=output,
                input_preview=prompt,
                logs=[
                    f"Prepared {len(prepared['resolved_inputs'])} resolved input(s) for llm_review."
                ],
            )
        except Exception as exc:  # pragma: no cover - defensive path
            return self.handle_error(exc)

    def _resolve_adapter(self, config: dict[str, Any]) -> LLMCompletionAdapter:
        provider = self._optional_str(config.get("provider"))
        if provider and provider in self._adapters_by_provider:
            return self._adapters_by_provider[provider]
        return self._default_adapter

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _resolve_input_definition(
        self,
        *,
        raw_input_definition: Any,
        prepared: dict[str, Any],
    ) -> str | None:
        definition_text = self._optional_str(raw_input_definition)
        if definition_text is None:
            return None

        if definition_text.startswith("ref:"):
            return self._resolve_single_reference_definition(definition_text, prepared)

        resolved_multi_refs = self._resolve_multi_reference_definition(definition_text, prepared)
        if resolved_multi_refs is not None:
            return resolved_multi_refs

        return definition_text

    def _resolve_single_reference_definition(self, definition_text: str, prepared: dict[str, Any]) -> str:
        ref_text = definition_text[len("ref:") :].strip()
        resolved_value = self._resolve_reference_value(ref_text=ref_text, prepared=prepared)
        if resolved_value is None:
            return ""
        return resolved_value

    def _resolve_multi_reference_definition(
        self,
        definition_text: str,
        prepared: dict[str, Any],
    ) -> str | None:
        pattern = re.compile(r"\[(?P<title>参照ノード)\s*:\s*(?P<refs>[^\]]*)\]")
        match = pattern.search(definition_text)
        if match is None:
            return None

        refs = [
            item.strip()
            for item in str(match.group("refs") or "").split(",")
            if item.strip()
        ]
        if not refs:
            return definition_text

        formatted_refs: list[str] = []
        for ref in refs:
            normalized_ref = re.sub(r"^ref:\s*", "", ref, flags=re.IGNORECASE).strip()
            resolved = self._resolve_reference_value(ref_text=normalized_ref, prepared=prepared)
            rendered = resolved if resolved is not None else "(not found)"
            if "\n" in rendered:
                formatted_refs.append(f"- {normalized_ref}:\n{textwrap.indent(rendered, '  ')}")
            else:
                formatted_refs.append(f"- {normalized_ref}: {rendered}")

        resolved_block = "\n".join([f"[{match.group('title')}]", *formatted_refs])
        prefix = definition_text[: match.start()].strip()
        suffix = definition_text[match.end() :].strip()

        sections: list[str] = []
        if prefix:
            sections.append(prefix)
        sections.append(resolved_block)
        if suffix:
            sections.append(suffix)
        return "\n\n".join(sections)

    def _resolve_reference_value(self, *, ref_text: str, prepared: dict[str, Any]) -> str | None:
        if "." not in ref_text:
            return None

        source_node_id, output_key = ref_text.split(".", 1)
        source_node_id = source_node_id.strip()
        output_key = output_key.strip()
        if not source_node_id or not output_key:
            return None

        node_outputs = prepared.get("node_outputs") or {}
        source_output = node_outputs.get(source_node_id)
        if not isinstance(source_output, dict):
            return None
        value = source_output.get(output_key)
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return str(value)

    def _build_prompt(
        self,
        *,
        prompt: str,
        input_definition: str | None,
        resolved_inputs: dict[str, Any],
        output_format: str | None,
    ) -> str:
        sections = [prompt]
        if input_definition:
            sections.append(f"Input definition:\n{input_definition}")
        if resolved_inputs:
            sections.append(
                "Resolved inputs:\n"
                + json.dumps(resolved_inputs, ensure_ascii=False, indent=2, default=str)
            )
        if output_format:
            sections.append(f"Output format:\n{output_format}")
        return "\n\n".join(sections)

    def _parse_structured_output(self, text: str, output_format: str | None) -> Any | None:
        if not output_format:
            return None
        normalized = output_format.strip().lower()
        if "json" not in normalized:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
