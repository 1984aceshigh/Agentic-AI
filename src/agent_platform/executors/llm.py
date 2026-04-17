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
from agent_platform.integrations.memory_contracts import MemoryQuery, MemoryScope, MemoryStore, MemoryWriteRequest
from agent_platform.integrations.profile_resolver import ProfileResolver
from agent_platform.integrations.rag_contracts import RetrievalQuery, VectorRetriever


class LLMExecutor(BaseNodeExecutor):
    node_type = "llm"

    def __init__(
        self,
        *,
        adapters_by_provider: Mapping[str, LLMCompletionAdapter] | None = None,
        default_adapter: LLMCompletionAdapter | None = None,
        stores_by_profile_name: Mapping[str, MemoryStore] | None = None,
        retrievers_by_profile_name: Mapping[str, VectorRetriever] | None = None,
        profile_resolver: ProfileResolver | None = None,
    ) -> None:
        self._adapters_by_provider = {
            str(provider): adapter for provider, adapter in (adapters_by_provider or {}).items()
        }
        self._default_adapter = default_adapter or DummyEchoLLMAdapter()
        self._stores_by_profile_name = dict(stores_by_profile_name or {})
        self._retrievers_by_profile_name = retrievers_by_profile_name or {}
        self._profile_resolver = profile_resolver or ProfileResolver()

    def execute(
        self,
        *,
        spec: Any,
        node: Any,
        context: Any | None,
        prepared_input: dict[str, Any],
    ) -> ExecutorResult:
        config = prepared_input.get("node_config", {})
        task = self._normalize_task(config.get("task"))

        try:
            profile = self._resolve_llm_profile(spec=spec, config=config)
            memory_records = self._read_memory(config=config, context=context)
            rag_hits = self._retrieve_rag(config=config, context=context, prepared_input=prepared_input)

            prompt = self._build_prompt(
                config=config,
                prepared_input=prepared_input,
                task=task,
                memory_records=memory_records,
                rag_hits=rag_hits,
            )
            adapter = self._resolve_adapter(config=config, profile=profile)
            response = adapter.complete(
                LLMCompletionRequest(
                    prompt=prompt,
                    system_prompt=self._optional_str(config.get("system_prompt")),
                    model=self._optional_str(config.get("model") or _get_attr_or_key(profile, "model")),
                    temperature=self._resolve_temperature(task=task, config=config, profile=profile),
                    max_tokens=self._optional_int(config.get("max_tokens") or _get_attr_or_key(profile, "max_tokens")),
                )
            )

            output = self._build_task_output(
                task=task,
                config=config,
                response_text=response.text,
            )
            if rag_hits:
                output["rag"] = {"hits": rag_hits, "count": len(rag_hits)}
            if memory_records:
                output["memory"] = {"records": memory_records, "count": len(memory_records)}

            self._write_memory(config=config, context=context, node=node, output=output)
            return ExecutorResult(
                status="SUCCEEDED",
                output=output,
                input_preview=prompt,
                logs=[f"llm task={task} executed"],
            )
        except Exception as exc:
            return self.handle_error(exc, spec=spec, node=node, context=context)

    def _resolve_llm_profile(self, *, spec: Any, config: Mapping[str, Any]) -> Any | None:
        profile_name = self._optional_str(config.get("llm_profile"))
        if not profile_name or spec is None:
            return None
        return self._profile_resolver.resolve_llm_profile(spec, profile_name)

    def _resolve_adapter(self, *, config: Mapping[str, Any], profile: Any | None) -> LLMCompletionAdapter:
        provider = self._optional_str(config.get("provider") or _get_attr_or_key(profile, "provider"))
        if provider and provider in self._adapters_by_provider:
            return self._adapters_by_provider[provider]
        return self._default_adapter

    def _build_prompt(
        self,
        *,
        config: Mapping[str, Any],
        prepared_input: Mapping[str, Any],
        task: str,
        memory_records: list[dict[str, Any]],
        rag_hits: list[dict[str, Any]],
    ) -> str:
        prompt = str(config.get("prompt") or config.get("prompt_template") or f"{task} by llm node").strip()
        resolved_inputs = prepared_input.get("resolved_inputs") or {}
        input_definition = self._resolve_input_definition(
            raw_input_definition=config.get("input_definition"),
            prepared_input=prepared_input,
        )
        output_format = self._optional_str(config.get("output_format"))
        assessment_options = _string_list(config.get("assessment_options"))
        extract_fields = _string_list(config.get("extract_fields"))
        extract_output_format = self._optional_str(config.get("extract_output_format"))
        sections = [prompt]
        if input_definition:
            sections.append(f"Input definition:\n{input_definition}")
        if resolved_inputs:
            sections.append("Resolved inputs:\n" + json.dumps(resolved_inputs, ensure_ascii=False, indent=2, default=str))
        if output_format:
            sections.append(f"Output format:\n{output_format}")
        if task == "assessment" and assessment_options:
            sections.append(
                "Assessment options:\n"
                + "\n".join(f"- {option}" for option in assessment_options)
                + "\n\nReturn one option as selected_option."
            )
        if task == "extract" and extract_fields:
            sections.append("Extract fields:\n" + "\n".join(f"- {field_name}" for field_name in extract_fields))
            sections.append(f"Extract output format: {extract_output_format or 'json'}")
        if memory_records:
            sections.append("Memory context:\n" + json.dumps(memory_records, ensure_ascii=False, indent=2, default=str))
        if rag_hits:
            sections.append("RAG context:\n" + json.dumps(rag_hits, ensure_ascii=False, indent=2, default=str))
        return "\n\n".join(sections)

    def _build_task_output(
        self,
        *,
        task: str,
        config: Mapping[str, Any],
        response_text: str,
    ) -> dict[str, Any]:
        if task == "assessment":
            options = _string_list(config.get("assessment_options"))
            selected_option = self._select_assessment_option(response_text=response_text, options=options)
            output: dict[str, Any] = {
                "review": response_text,
                "task": task,
                "selected_option": selected_option,
                "assessment_options": options,
                "score": 80,
            }
            routes = config.get("assessment_routes")
            if isinstance(routes, Mapping) and selected_option:
                next_node = self._resolve_assessment_route(routes=routes, selected_option=selected_option)
                if isinstance(next_node, str) and next_node.strip():
                    output["next_node"] = next_node.strip()
            return output

        if task == "extract":
            extract_fields = _string_list(config.get("extract_fields"))
            extracted = self._extract_structured_fields(fields=extract_fields, text=response_text)
            output_format = self._normalize_extract_output_format(config.get("extract_output_format"))
            rendered = self._render_extract_output(extracted=extracted, output_format=output_format)
            return {
                "result": rendered,
                "task": task,
                "extracted": extracted,
                "extract_output_format": output_format,
            }

        return {
            "result": response_text,
            "task": task,
        }

    def _select_assessment_option(self, *, response_text: str, options: list[str]) -> str | None:
        if not options:
            return None
        lowered_response = response_text.lower()
        matched: list[tuple[int, str]] = []
        for option in options:
            option_lower = option.lower()
            idx = lowered_response.find(option_lower)
            if idx >= 0:
                matched.append((idx, option))
        if matched:
            matched.sort(key=lambda item: item[0])
            return matched[0][1]
        return options[0]

    def _resolve_assessment_route(self, *, routes: Mapping[Any, Any], selected_option: str) -> Any:
        direct = routes.get(selected_option)
        if direct is not None:
            return direct

        normalized_selected = str(selected_option).strip().lower()
        for key, value in routes.items():
            if str(key).strip().lower() == normalized_selected:
                return value
        return None

    def _extract_structured_fields(self, *, fields: list[str], text: str) -> dict[str, Any]:
        if not fields:
            return {"text": text}
        extracted: dict[str, Any] = {}
        for field_name in fields:
            pattern = re.compile(rf"{re.escape(field_name)}\s*[:：]\s*(?P<value>.+)", re.IGNORECASE)
            match = pattern.search(text)
            extracted[field_name] = str(match.group("value")).strip() if match is not None else ""
        return extracted

    def _normalize_extract_output_format(self, raw_value: Any) -> str:
        normalized = str(raw_value or "json").strip().lower()
        if normalized == "plain text":
            normalized = "plain_text"
        if normalized in {"json", "yaml", "markdown", "plain_text"}:
            return normalized
        return "json"

    def _render_extract_output(self, *, extracted: Mapping[str, Any], output_format: str) -> str:
        if output_format == "yaml":
            try:
                import yaml

                return yaml.safe_dump(dict(extracted), allow_unicode=True, sort_keys=False).strip()
            except Exception:
                return json.dumps(extracted, ensure_ascii=False, indent=2, default=str)
        if output_format == "markdown":
            return "\n".join(f"- **{key}**: {value}" for key, value in extracted.items())
        if output_format == "plain_text":
            return "\n".join(f"{key}: {value}" for key, value in extracted.items())
        return json.dumps(extracted, ensure_ascii=False, indent=2, default=str)

    def _resolve_temperature(self, *, task: str, config: Mapping[str, Any], profile: Any | None) -> float | None:
        explicit = self._optional_float(config.get("temperature"))
        if explicit is not None:
            return explicit

        if task in {"assessment", "extract"}:
            # 判定・抽出は揺らぎを抑えるため既定を 0 とする
            return 0.0

        profile_temperature = self._optional_float(_get_attr_or_key(profile, "temperature"))
        if profile_temperature is not None:
            return profile_temperature

        return 0.0

    def _resolve_input_definition(
        self,
        *,
        raw_input_definition: Any,
        prepared_input: Mapping[str, Any],
    ) -> str | None:
        definition_text = self._optional_str(raw_input_definition)
        if definition_text is None:
            return None

        if definition_text.startswith("ref:"):
            return self._resolve_single_reference_definition(definition_text, prepared_input)

        resolved_multi_refs = self._resolve_multi_reference_definition(definition_text, prepared_input)
        if resolved_multi_refs is not None:
            return resolved_multi_refs

        return definition_text

    def _resolve_single_reference_definition(
        self,
        definition_text: str,
        prepared_input: Mapping[str, Any],
    ) -> str:
        ref_text = definition_text[len("ref:") :].strip()
        resolved_value = self._resolve_reference_value(ref_text=ref_text, prepared_input=prepared_input)
        if resolved_value is None:
            return ""
        return resolved_value

    def _resolve_multi_reference_definition(
        self,
        definition_text: str,
        prepared_input: Mapping[str, Any],
    ) -> str | None:
        pattern = re.compile(r"\[(?P<title>参照ノード)\s*:\s*(?P<refs>[^\]]*)\]")
        match = pattern.search(definition_text)
        if match is None:
            return None

        refs = [item.strip() for item in str(match.group("refs") or "").split(",") if item.strip()]
        if not refs:
            return definition_text

        formatted_refs: list[str] = []
        for ref in refs:
            normalized_ref = re.sub(r"^ref:\s*", "", ref, flags=re.IGNORECASE).strip()
            resolved = self._resolve_reference_value(ref_text=normalized_ref, prepared_input=prepared_input)
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

    def _resolve_reference_value(self, *, ref_text: str, prepared_input: Mapping[str, Any]) -> str | None:
        if "." not in ref_text:
            return None

        source_node_id, output_key = ref_text.split(".", 1)
        source_node_id = source_node_id.strip()
        output_key = output_key.strip()
        if not source_node_id or not output_key:
            return None

        node_outputs = prepared_input.get("node_outputs") or {}
        if not isinstance(node_outputs, Mapping):
            return None
        source_output = node_outputs.get(source_node_id)
        if not isinstance(source_output, Mapping):
            return None
        value = source_output.get(output_key)
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return str(value)

    def _read_memory(self, *, config: Mapping[str, Any], context: Any | None) -> list[dict[str, Any]]:
        memory = config.get("memory")
        if not isinstance(memory, Mapping):
            return []
        read_cfg = memory.get("read")
        if not isinstance(read_cfg, Mapping):
            return []
        profile = self._optional_str(read_cfg.get("profile"))
        if not profile:
            return []
        store = self._stores_by_profile_name.get(profile)
        if store is None:
            raise ValueError(f"memory.read.profile '{profile}' に対応する store がありません。")
        scope = MemoryScope(str(read_cfg.get("scope") or "workflow"))
        tags = _string_list(read_cfg.get("tags"))
        limit = int(read_cfg.get("limit") or 5)
        query = MemoryQuery(
            scope=scope,
            workflow_id=getattr(context, "workflow_id", None),
            execution_id=getattr(context, "execution_id", None) if scope == MemoryScope.EXECUTION else None,
            tags=tags,
            limit=limit,
        )
        return [item.model_dump(mode="json") for item in store.read(query)]

    def _write_memory(
        self,
        *,
        config: Mapping[str, Any],
        context: Any | None,
        node: Any,
        output: Mapping[str, Any],
    ) -> None:
        memory = config.get("memory")
        if not isinstance(memory, Mapping):
            return
        write_cfg = memory.get("write")
        if not isinstance(write_cfg, Mapping):
            return
        if not bool(write_cfg.get("enabled")):
            return
        profile = self._optional_str(write_cfg.get("profile"))
        if not profile:
            return
        store = self._stores_by_profile_name.get(profile)
        if store is None:
            raise ValueError(f"memory.write.profile '{profile}' に対応する store がありません。")
        scope = MemoryScope(str(write_cfg.get("scope") or "workflow"))
        content_template = write_cfg.get("content_template")
        content: dict[str, Any]
        if isinstance(content_template, Mapping):
            content = dict(content_template)
        else:
            content = {
                "node_id": _get_attr_or_key(node, "id"),
                "output": dict(output),
            }
        request = MemoryWriteRequest(
            scope=scope,
            workflow_id=getattr(context, "workflow_id", None),
            execution_id=getattr(context, "execution_id", None) if scope == MemoryScope.EXECUTION else None,
            tags=_string_list(write_cfg.get("tags")),
            content=content,
        )
        store.write(request)

    def _retrieve_rag(
        self,
        *,
        config: Mapping[str, Any],
        context: Any | None,
        prepared_input: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        rag = config.get("rag")
        if not isinstance(rag, Mapping):
            return []
        profile = self._optional_str(rag.get("profile"))
        if not profile:
            return []
        retriever = self._retrievers_by_profile_name.get(profile)
        if retriever is None:
            raise ValueError(f"rag.profile '{profile}' に対応する retriever がありません。")
        query = self._resolve_query(rag.get("query"), prepared_input=prepared_input, context=context)
        if not query:
            query = self._extract_rag_query_from_prompt(
                config=config,
                prepared_input=prepared_input,
                context=context,
            )
        if not query:
            return []
        top_k = int(rag.get("top_k") or 5)
        hits = retriever.retrieve(RetrievalQuery(query_text=query, top_k=top_k))
        return [hit.model_dump(mode="json") for hit in hits]

    def _extract_rag_query_from_prompt(
        self,
        *,
        config: Mapping[str, Any],
        prepared_input: Mapping[str, Any],
        context: Any | None,
    ) -> str:
        prompt = self._resolve_query(
            config.get("prompt") or config.get("prompt_template") or "",
            prepared_input=prepared_input,
            context=context,
        )
        input_definition = self._resolve_input_definition(
            raw_input_definition=config.get("input_definition"),
            prepared_input=prepared_input,
        )
        resolved_inputs = prepared_input.get("resolved_inputs")
        parts: list[str] = []
        if prompt:
            parts.append(str(prompt))
        if input_definition:
            parts.append(str(input_definition))
        if isinstance(resolved_inputs, Mapping):
            parts.extend(str(value) for value in resolved_inputs.values() if value is not None)
        query = "\n".join(item.strip() for item in parts if str(item).strip())
        return query[:1200].strip()

    def _resolve_query(self, raw: Any, *, prepared_input: Mapping[str, Any], context: Any | None) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            pattern = re.compile(r"\{\{\s*(?P<expr>[^}]+)\s*\}\}")

            def _replace(match: re.Match[str]) -> str:
                expr = match.group("expr").strip()
                if expr.startswith("input."):
                    key = expr.split(".", 1)[1]
                    return str((prepared_input.get("resolved_inputs") or {}).get(key, ""))
                if expr.startswith("global."):
                    key = expr.split(".", 1)[1]
                    return str((prepared_input.get("global_inputs") or {}).get(key, ""))
                if expr.startswith("context."):
                    key = expr.split(".", 1)[1]
                    return str(getattr(context, key, ""))
                return ""

            return pattern.sub(_replace, raw).strip()
        return str(raw).strip()

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

    def _normalize_task(self, raw_task: Any) -> str:
        normalized = str(raw_task or "generate").strip().lower()
        if normalized in {"generate", "assessment", "extract"}:
            return normalized
        if normalized in {"review", "classify", "judge"}:
            return "assessment"
        return "generate"


def _get_attr_or_key(obj: Any, field_name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]
