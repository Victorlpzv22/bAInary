"""Tests for bainary.rag — unit tests with HashMockEmbeddings + InMemoryStore, no network."""

from __future__ import annotations

from bainary.lift.artifact import Function
from bainary.lift.errors import BainaryError
from bainary.rag import RagError
from bainary.rag.errors import RagError as RagErrorDirect
from bainary.rag.text import TEXT_VERSION, build_text


def test_rag_error_is_bainary_error():
    assert issubclass(RagError, BainaryError)
    assert RagError is RagErrorDirect


def test_text_version_is_string():
    assert isinstance(TEXT_VERSION, str)
    assert TEXT_VERSION


def test_build_text_includes_name_and_signature():
    fn = Function(
        address="0x1000",
        name="main",
        signature="int main(int argc, char ** argv)",
        calling_convention="cdecl",
        size_bytes=64,
        assembly="ret",
        pseudocode="int main() { return 0; }",
    )
    text = build_text(fn)
    assert "main" in text
    assert "int main(int argc, char ** argv)" in text
    assert "int main() { return 0; }" in text


def test_build_text_falls_back_to_assembly_when_no_pseudocode():
    fn = Function(
        address="0x2000",
        name="add",
        signature="int add(void)",
        calling_convention="cdecl",
        size_bytes=8,
        assembly="mov eax, 1\nret",
        pseudocode=None,
    )
    text = build_text(fn)
    assert "mov eax, 1" in text
    assert "no decompilation available" in text.lower()


def test_build_text_empty_when_no_pseudocode_and_no_assembly():
    fn = Function(
        address="0x3000",
        name="stub",
        signature="void stub(void)",
        calling_convention="cdecl",
        size_bytes=0,
        assembly="",
        pseudocode=None,
    )
    assert build_text(fn) == ""
