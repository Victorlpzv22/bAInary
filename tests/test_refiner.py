"""Tests for bainary.refine — unit tests with MockClient, no network."""

from __future__ import annotations

import pytest

from bainary.graph import CallGraph
from bainary.lift.artifact import BinaryArtifact
from bainary.refine import (
    AnthropicClient,
    LLMClient,
    MockClient,
    OpenAICompatibleClient,
    RefineError,
    Refiner,
    create_client,
)
from bainary.refine.cache import RefinementCache
from bainary.refine.errors import RefineError as RefineErrorDirect
from bainary.refine.prompts import PROMPT_VERSION, build_prompt


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


def test_prompt_version_is_string():
    assert isinstance(PROMPT_VERSION, str)
    assert len(PROMPT_VERSION) > 0


def test_prompt_contains_function_name():
    prompt = build_prompt("main", "int main() { return 0; }")
    assert "main" in prompt


def test_prompt_contains_pseudo_c():
    prompt = build_prompt("main", "int main() { return 0; }")
    assert "int main() { return 0; }" in prompt


def test_prompt_contains_callers():
    prompt = build_prompt("main", "int main() {}", caller_names=["_start"])
    assert "_start" in prompt


def test_prompt_contains_callees():
    prompt = build_prompt("main", "int main() {}", callee_names=["add", "mul", "printf"])
    assert "add" in prompt
    assert "mul" in prompt
    assert "printf" in prompt


def test_prompt_no_callgraph_context():
    prompt = build_prompt("main", "int main() {}")
    assert "unknown" in prompt.lower()


def test_prompt_has_refinement_instructions():
    prompt = build_prompt("main", "int main() {}")
    assert "rename" in prompt.lower()
    assert "comment" in prompt.lower()
    assert "code block" in prompt.lower()


def test_cache_miss_returns_none(tmp_path):
    cache = RefinementCache(tmp_path)
    assert cache.lookup("nonexistent_key") is None


def test_cache_store_and_lookup(tmp_path):
    cache = RefinementCache(tmp_path)
    cache.store("key123", "void _fini(void) { return; }")
    hit = cache.lookup("key123")
    assert hit is not None
    assert "void _fini" in hit


def test_cache_invalidation_on_model_change(tmp_path):
    cache_a = RefinementCache(tmp_path, model="kimi-k2.7-code")
    cache_a.store("key456", "refined code here")
    assert cache_a.lookup("key456") is not None

    cache_b = RefinementCache(tmp_path, model="glm-5.2")
    assert cache_b.lookup("key456") is None


def test_cache_count(tmp_path):
    cache = RefinementCache(tmp_path)
    assert cache.count() == 0
    cache.store("a", "code a")
    cache.store("b", "code b")
    assert cache.count() == 2


def test_cache_clear(tmp_path):
    cache = RefinementCache(tmp_path)
    cache.store("a", "code a")
    cache.store("b", "code b")
    cache.clear()
    assert cache.lookup("a") is None
    assert cache.lookup("b") is None
    assert cache.count() == 0


# --- Refiner tests ---


def _fn_dict(
    address: str,
    name: str,
    callees: list[dict] | None = None,
    is_thunk: bool = False,
    pseudocode: str | None = "// stub",
    size_bytes: int = 16,
    pseudocode_error: str | None = None,
) -> dict:
    return {
        "address": address,
        "name": name,
        "signature": f"int {name}(void)",
        "calling_convention": "cdecl",
        "size_bytes": size_bytes,
        "is_thunk": is_thunk,
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": callees or [],
        "assembly": "ret",
        "pseudocode": pseudocode,
        "pseudocode_error": pseudocode_error,
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    }


def _make_artifact(functions: list[dict]) -> BinaryArtifact:
    return BinaryArtifact.from_dict(
        {
            "schema_version": "1.0",
            "binary": {
                "path": "/tmp/test.elf",
                "sha256": "ab" * 32,
                "format": "ELF",
                "arch": "x64",
                "endianness": "little",
                "entry_point": "0x401000",
                "base_address": "0x400000",
                "decompiler_version": "test",
            },
            "sections": [],
            "imports": [],
            "exports": [],
            "strings": [],
            "functions": functions,
        }
    )


def _test_artifact() -> BinaryArtifact:
    return _make_artifact(
        [
            _fn_dict(
                "0x1000",
                "main",
                callees=[{"address": "0x2000", "name": "add", "is_external": False}],
                pseudocode="int main() { int iVar1 = add(1); return iVar1; }",
            ),
            _fn_dict("0x2000", "add", pseudocode="int add(int a) { return a + 1; }"),
            _fn_dict("0x3000", "_fini", is_thunk=True, pseudocode="void _fini(void) { return; }"),
            _fn_dict("0x4000", "no_pseudo", pseudocode=None, pseudocode_error="decompile failed"),
        ]
    )


def test_refine_basic(tmp_path):
    mock = MockClient(
        responses={
            "main": "int main() { int result = add(1); return result; }",
            "add": "int add(int a) { return a + 1; }",
        }
    )
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refined = refiner.refine(artifact)
    main_fn = next(f for f in refined.functions if f.name == "main")
    assert "result" in main_fn.pseudocode
    assert "iVar1" not in main_fn.pseudocode


def test_refine_preserves_original(tmp_path):
    mock = MockClient(responses={"main": "refined main", "add": "refined add"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    original = _test_artifact()
    original_main = original.functions[0].pseudocode
    refiner.refine(original)
    assert original.functions[0].pseudocode == original_main


def test_refine_skip_thunks(tmp_path):
    mock = MockClient(responses={"_fini": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"), skip_thunks=True)
    artifact = _test_artifact()
    refined = refiner.refine(artifact)
    fini = next(f for f in refined.functions if f.name == "_fini")
    assert fini.pseudocode == "void _fini(void) { return; }"


def test_refine_skip_no_pseudocode(tmp_path):
    mock = MockClient(responses={"no_pseudo": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refined = refiner.refine(artifact)
    no_pseudo = next(f for f in refined.functions if f.name == "no_pseudo")
    assert no_pseudo.pseudocode is None


def test_refine_min_size(tmp_path):
    mock = MockClient(responses={"add": "refined add"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"), min_size=20)
    artifact = _test_artifact()
    refined = refiner.refine(artifact)
    add_fn = next(f for f in refined.functions if f.name == "add")
    assert add_fn.pseudocode == "int add(int a) { return a + 1; }"


def test_refine_with_callgraph(tmp_path):
    mock = MockClient(
        responses={
            "main": "refined main",
            "add": "refined add",
        }
    )
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    cg = CallGraph.from_artifact(artifact)
    refiner.refine(artifact, cg)
    main_prompt = next(p for p in mock.calls if "main" in p and "Refine" in p)
    assert "add" in main_prompt


def test_refine_without_callgraph(tmp_path):
    mock = MockClient(
        responses={
            "main": "refined main",
            "add": "refined add",
        }
    )
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refiner.refine(artifact)
    main_prompt = next(p for p in mock.calls if "main" in p and "Refine" in p)
    assert "unknown" in main_prompt.lower()


def test_refine_llm_failure(tmp_path):
    """If the LLM fails for one function, others still get refined."""
    mock = MockClient(responses={"add": "refined add"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refined = refiner.refine(artifact)
    add_fn = next(f for f in refined.functions if f.name == "add")
    assert add_fn.pseudocode == "refined add"


def test_refine_cache_hit(tmp_path):
    mock = MockClient(
        responses={
            "main": "refined main",
            "add": "refined add",
        }
    )
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refiner.refine(artifact)
    first_count = mock.call_count
    refiner.refine(artifact)
    assert mock.call_count == first_count


def test_refine_cache_hit_with_explicit_cache(tmp_path):
    mock = MockClient(
        responses={
            "main": "refined main",
            "add": "refined add",
        }
    )
    cache = RefinementCache(tmp_path, model="mock")
    refiner = Refiner(client=mock, cache=cache)
    artifact = _test_artifact()
    refiner.refine(artifact)
    first_count = mock.call_count
    refiner.refine(artifact)
    assert mock.call_count == first_count


# --- refine_one (single-function refinement, used by GUI subsystem E) ---


def test_refine_one_single_function(tmp_path):
    """refine_one refines one function and returns its code (no artifact mutation)."""
    mock = MockClient(responses={"main": "int main() { return result; }"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    main = artifact.functions[0]
    refined_code = refiner.refine_one(main, CallGraph.from_artifact(artifact))
    assert refined_code == "int main() { return result; }"
    # original artifact untouched
    assert "result" not in (artifact.functions[0].pseudocode or "")


def test_refine_one_skip_when_filtered(tmp_path):
    """refine_one returns None when the function is filtered out (skip_thunks)."""
    mock = MockClient(responses={"_fini": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"), skip_thunks=True)
    artifact = _test_artifact()
    fini = next(f for f in artifact.functions if f.name == "_fini")
    assert refiner.refine_one(fini) is None
    assert mock.call_count == 0


def test_refine_one_returns_none_for_no_pseudocode(tmp_path):
    """refine_one returns None when the function has no pseudocode."""
    mock = MockClient(responses={"no_pseudo": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    no_pseudo = next(f for f in artifact.functions if f.name == "no_pseudo")
    assert refiner.refine_one(no_pseudo) is None
    assert mock.call_count == 0


def test_refine_one_respects_min_size(tmp_path):
    """refine_one returns None when size_bytes < min_size."""
    mock = MockClient(responses={"add": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"), min_size=100)
    artifact = _test_artifact()
    add = next(f for f in artifact.functions if f.name == "add")
    assert refiner.refine_one(add) is None
    assert mock.call_count == 0


def test_refine_one_uses_cache(tmp_path):
    """refine_one hits cache on second call without re-invoking the LLM."""
    mock = MockClient(responses={"main": "refined main"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refiner.refine_one(artifact.functions[0])
    first_count = mock.call_count
    refiner.refine_one(artifact.functions[0])
    assert mock.call_count == first_count


def test_refine_one_without_callgraph(tmp_path):
    """refine_one works without a call graph (callers/callees unknown)."""
    mock = MockClient(responses={"main": "refined main no cg"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refined_code = refiner.refine_one(artifact.functions[0])
    assert refined_code == "refined main no cg"
    assert "unknown" in mock.calls[0].lower()


def test_refine_one_llm_error_returns_none(tmp_path):
    """refine_one returns None when the LLM raises (function preserved elsewhere)."""

    class FailClient(MockClient):
        def complete(self, *a, **k):
            raise RefineError("boom")

    refiner = Refiner(
        client=FailClient(responses={}), cache=RefinementCache(tmp_path, model="mock")
    )
    artifact = _test_artifact()
    assert refiner.refine_one(artifact.functions[0]) is None


def test_refine_one_empty_response_returns_none(tmp_path):
    """refine_one returns None when the LLM returns an empty string."""

    class EmptyClient(MockClient):
        def complete(self, *a, **k):
            return ""

    refiner = Refiner(
        client=EmptyClient(responses={}), cache=RefinementCache(tmp_path, model="mock")
    )
    artifact = _test_artifact()
    assert refiner.refine_one(artifact.functions[0]) is None
