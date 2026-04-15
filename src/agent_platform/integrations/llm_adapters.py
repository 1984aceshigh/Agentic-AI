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

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        content = (response.choices[0].message.content or "").strip()
        raw = response.model_dump(mode="python") if hasattr(response, "model_dump") else {"response": str(response)}
        return LLMCompletionResponse(text=content, raw=raw)
