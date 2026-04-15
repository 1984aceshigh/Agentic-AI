from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RuntimeLLMConfig:
    provider: str = "dummy"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None


def load_runtime_llm_config(config_path: Path) -> RuntimeLLMConfig:
    """Load runtime LLM config from yaml file + environment overrides."""

    file_data: dict[str, object] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            file_data = loaded

    llm_data = file_data.get("llm")
    if not isinstance(llm_data, dict):
        llm_data = {}

    file_provider = _as_text(llm_data.get("provider"))
    file_model = _as_text(llm_data.get("openai_model"))
    file_api_key = _as_text(llm_data.get("openai_api_key"))

    provider = (
        _as_text(os.getenv("AGENT_PLATFORM_LLM_PROVIDER"))
        or file_provider
        or "dummy"
    ).strip().lower()
    openai_model = _as_text(os.getenv("OPENAI_MODEL")) or file_model or "gpt-4o-mini"
    openai_api_key = _as_text(os.getenv("OPENAI_API_KEY")) or file_api_key

    return RuntimeLLMConfig(
        provider=provider,
        openai_model=openai_model,
        openai_api_key=openai_api_key,
    )


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
