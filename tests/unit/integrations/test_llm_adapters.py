from __future__ import annotations

import sys
from types import SimpleNamespace

from agent_platform.integrations.llm_adapters import LLMCompletionRequest, OpenAIChatCompletionAdapter


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            model_dump=lambda mode="python": {"ok": True},
        )


class _FakeClient:
    def __init__(self, completions: _FakeChatCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _install_fake_openai_module(completions: _FakeChatCompletions) -> None:
    class _FakeOpenAI:  # noqa: N801 - mimic external SDK naming
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.chat = _FakeClient(completions).chat

    sys.modules["openai"] = SimpleNamespace(OpenAI=_FakeOpenAI)


def test_openai_adapter_uses_max_completion_tokens_for_gpt5_models() -> None:
    completions = _FakeChatCompletions()
    _install_fake_openai_module(completions)
    adapter = OpenAIChatCompletionAdapter(api_key="test")

    adapter.complete(
        LLMCompletionRequest(
            prompt="hello",
            model="gpt-5-nano",
            max_tokens=123,
        )
    )

    assert completions.last_kwargs is not None
    assert completions.last_kwargs.get("max_completion_tokens") == 123
    assert "max_tokens" not in completions.last_kwargs


def test_openai_adapter_uses_max_tokens_for_non_gpt5_models() -> None:
    completions = _FakeChatCompletions()
    _install_fake_openai_module(completions)
    adapter = OpenAIChatCompletionAdapter(api_key="test")

    adapter.complete(
        LLMCompletionRequest(
            prompt="hello",
            model="gpt-4o-mini",
            max_tokens=456,
        )
    )

    assert completions.last_kwargs is not None
    assert completions.last_kwargs.get("max_tokens") == 456
    assert "max_completion_tokens" not in completions.last_kwargs


def test_openai_adapter_omits_optional_params_when_none() -> None:
    completions = _FakeChatCompletions()
    _install_fake_openai_module(completions)
    adapter = OpenAIChatCompletionAdapter(api_key="test")

    adapter.complete(
        LLMCompletionRequest(
            prompt="hello",
            model="gpt-5.4-nano",
            temperature=None,
            max_tokens=None,
        )
    )

    assert completions.last_kwargs is not None
    assert "temperature" not in completions.last_kwargs
    assert "max_tokens" not in completions.last_kwargs
    assert "max_completion_tokens" not in completions.last_kwargs


def test_openai_adapter_omits_temperature_for_gpt5_even_when_specified() -> None:
    completions = _FakeChatCompletions()
    _install_fake_openai_module(completions)
    adapter = OpenAIChatCompletionAdapter(api_key="test")

    adapter.complete(
        LLMCompletionRequest(
            prompt="hello",
            model="gpt-5-nano",
            temperature=0.0,
            max_tokens=100,
        )
    )

    assert completions.last_kwargs is not None
    assert "temperature" not in completions.last_kwargs
    assert completions.last_kwargs.get("max_completion_tokens") == 100
