# mypy: ignore-errors
"""LLM client abstraction with multiple provider support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bainary.refine.errors import RefineError


class LLMClient(ABC):
    """Abstract interface for LLM completion calls."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier (e.g. 'kimi-k2.7-code')."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """Send a prompt to the LLM and return the completion text.

        Raises
        ------
        RefineError
            If the LLM call fails (HTTP error, timeout, etc.).
        """


class MockClient(LLMClient):
    """Deterministic mock client for tests. No network, no API key."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self._call_count = 0
        self._calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def calls(self) -> list[str]:
        return self._calls

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        self._call_count += 1
        self._calls.append(prompt)
        for key, response in self._responses.items():
            if key in prompt:
                return response
        return "/* refined */\nvoid unknown(void) { return; }"


class OpenAICompatibleClient(LLMClient):
    """Client for OpenAI-compatible APIs (OpenAI, OpenCode Go, Ollama, etc.)."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o",
    ) -> None:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            err_str = str(e).lower()
            if "temperature" in err_str and "400" in err_str:
                response = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=1,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                raise RefineError(f"OpenAI-compatible LLM call failed: {e}") from e
        content = response.choices[0].message.content or ""
        return content


class AnthropicClient(LLMClient):
    """Client for Anthropic-compatible APIs (Anthropic, OpenCode Go /v1/messages)."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        import anthropic

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            err_str = str(e).lower()
            if "temperature" in err_str:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=1,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                raise RefineError(f"Anthropic LLM call failed: {e}") from e
        text_parts = [block.text for block in response.content if hasattr(block, "text")]
        return "".join(text_parts)


def create_client(
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    responses: dict[str, str] | None = None,
) -> LLMClient:
    """Factory for creating an LLM client by provider name."""
    if provider == "mock":
        return MockClient(responses=responses)
    if provider == "openai":
        if not api_key:
            raise RefineError("api_key required for provider='openai'")
        return OpenAICompatibleClient(
            api_key=api_key,
            base_url=base_url,
            model=model or "gpt-4o",
        )
    if provider == "anthropic":
        if not api_key:
            raise RefineError("api_key required for provider='anthropic'")
        return AnthropicClient(
            api_key=api_key,
            base_url=base_url,
            model=model or "claude-3-5-sonnet-20241022",
        )
    raise RefineError(f"unknown provider {provider!r}; known: openai, anthropic, mock")
