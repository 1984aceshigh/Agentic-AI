from __future__ import annotations

from pathlib import Path

from agent_platform.runtime.app_config import load_runtime_llm_config


def test_load_runtime_llm_config_from_file(tmp_path: Path) -> None:
    config_file = tmp_path / "runtime.yaml"
    config_file.write_text(
        """
llm:
  provider: openai
  openai_model: gpt-4.1-mini
  openai_api_key: file-key
""".strip(),
        encoding="utf-8",
    )

    config = load_runtime_llm_config(config_file)

    assert config.provider == "openai"
    assert config.openai_model == "gpt-4.1-mini"


def test_load_runtime_llm_config_defaults_when_file_missing(tmp_path: Path) -> None:
    config = load_runtime_llm_config(tmp_path / "missing.yaml")

    assert config.provider == "dummy"
    assert config.openai_model == "gpt-4o-mini"

