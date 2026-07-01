"""Tests for bainary.refine — unit tests with MockClient, no network."""

from __future__ import annotations

import pytest

from bainary.refine import (
    AnthropicClient,
    LLMClient,
    MockClient,
    OpenAICompatibleClient,
    RefineError,
    create_client,
)
from bainary.refine.errors import RefineError as RefineErrorDirect


def test_refine_error_is_bainary_error():
    from bainary.lift.errors import BainaryError

    assert issubclass(RefineError, BainaryError)
    assert RefineError is RefineErrorDirect


def test_mock_client_is_llm_client():
    client = MockClient(responses={"foo": "int foo() { return 0; }"})
    assert isinstance(client, LLMClient)


def test_mock_client_returns_response():
    client = MockClient(responses={"_fini": "void _fini(void) { return; }"})
    result = client.complete("Refine this: _fini")
    assert "void _fini" in result
    assert client.model_name == "mock"


def test_mock_client_unknown_function():
    client = MockClient(responses={"foo": "int foo() {}"})
    result = client.complete("Refine this: bar")
    assert isinstance(result, str)


def test_create_client_mock():
    client = create_client(provider="mock", responses={"foo": "int foo() {}"})
    assert isinstance(client, MockClient)


def test_create_client_openai():
    client = create_client(
        provider="openai",
        api_key="sk-test",
        base_url="https://example.com/v1",
        model="gpt-4o",
    )
    assert isinstance(client, OpenAICompatibleClient)
    assert client.model_name == "gpt-4o"


def test_create_client_anthropic():
    client = create_client(
        provider="anthropic",
        api_key="sk-ant-test",
        base_url="https://example.com/v1",
        model="claude-3-5-sonnet-20241022",
    )
    assert isinstance(client, AnthropicClient)
    assert client.model_name == "claude-3-5-sonnet-20241022"


def test_create_client_unknown_provider():
    with pytest.raises(RefineError, match="unknown provider"):
        create_client(provider="gemini", api_key="x")
