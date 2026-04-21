from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LLMCompletionRequest:
    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(slots=True)
class LLMCompletionResponse:
    text: str
    raw: dict[str, Any]


class LLMCompletionAdapter(ABC):
    @abstractmethod
    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        """Execute an LLM completion request."""


class DummyEchoLLMAdapter(LLMCompletionAdapter):
    """Safe default adapter used for local/offline MVP execution."""

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        text = request.prompt
        return LLMCompletionResponse(text=text, raw={"provider": "dummy", "prompt": request.prompt})


class OpenAIChatCompletionAdapter(LLMCompletionAdapter):
    """Adapter for OpenAI Chat Completions API.

    The openai package is imported lazily so the rest of the app can run
    without OpenAI installed/configured.
    """

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key
        self._default_model = model

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local environment
            raise RuntimeError("openai package is not available") from exc

        client = OpenAI(api_key=self._api_key)
        model = request.model or self._default_model
        if not model:
            raise ValueError("model is required for OpenAI adapter")

        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if request.temperature is not None and _should_send_temperature(model=model, temperature=request.temperature):
            create_kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            # gpt-5 系モデルは chat.completions で max_tokens ではなく
            # max_completion_tokens を受け付けるため切り替える。
            if _uses_max_completion_tokens(model):
                create_kwargs["max_completion_tokens"] = request.max_tokens
            else:
                create_kwargs["max_tokens"] = request.max_tokens

        response = client.chat.completions.create(**create_kwargs)
        content = (response.choices[0].message.content or "").strip()
        raw = response.model_dump(mode="python") if hasattr(response, "model_dump") else {"response": str(response)}
        return LLMCompletionResponse(text=content, raw=raw)


def _uses_max_completion_tokens(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith("gpt-5")


def _should_send_temperature(*, model: str, temperature: float) -> bool:
    # gpt-5 系は現時点で temperature の自由指定を受け付けず、
    # 指定すると 400 unsupported_value となるため未送信にする。
    if _uses_max_completion_tokens(model):
        return False
    return True
