import pytest
from pydantic import ValidationError

from bainary.lift.schema import (
    SCHEMA_VERSION,
    BinaryArtifactSchema,
    CallingConvention,
    CallRefSchema,
    FunctionSchema,
)


def test_schema_version_constant():
    assert SCHEMA_VERSION == "1.0"


def test_minimal_artifact_validates():
    data = {
        "schema_version": SCHEMA_VERSION,
        "binary": {
            "path": "/tmp/x.elf",
            "sha256": "ab" * 32,
            "format": "ELF",
            "arch": "x64",
            "endianness": "little",
            "entry_point": "0x400000",
            "base_address": "0x400000",
            "decompiler_version": "ghidra-11.0.1",
        },
        "sections": [],
        "imports": [],
        "exports": [],
        "strings": [],
        "functions": [],
    }
    artifact = BinaryArtifactSchema.model_validate(data)
    assert artifact.binary.format == "ELF"
    assert artifact.binary.arch == "x64"
    assert artifact.binary.decompiler_version == "ghidra-11.0.1"


def test_format_enum_rejects_invalid():
    data = {
        "schema_version": SCHEMA_VERSION,
        "binary": {
            "path": "/tmp/x",
            "sha256": "a" * 64,
            "format": "WASM",  # invalid
            "arch": "x64",
            "endianness": "little",
            "entry_point": "0x0",
            "base_address": "0x0",
        },
        "sections": [],
        "imports": [],
        "exports": [],
        "strings": [],
        "functions": [],
    }
    with pytest.raises(ValidationError):
        BinaryArtifactSchema.model_validate(data)


def test_function_with_all_fields():
    fn = FunctionSchema.model_validate({
        "address": "0x401000",
        "name": "main",
        "signature": "int main(void)",
        "calling_convention": "cdecl",
        "size_bytes": 64,
        "is_thunk": False,
        "basic_blocks": [{
            "address": "0x401000",
            "instructions": [{
                "address": "0x401000",
                "bytes": "55 48 89 e5",
                "mnemonic": "push",
                "operands": ["rbp"],
                "comment": None,
            }],
            "successors": ["0x401004"],
            "terminator": "fall_through",
        }],
        "cfg": {
            "nodes": ["0x401000", "0x401004"],
            "edges": [["0x401000", "0x401004"]],
        },
        "callers": [{"address": "0x402000", "name": "caller"}],
        "callees": [{"address": "0x403000", "name": "puts", "is_external": True}],
        "assembly": "push rbp\nmov rbp,rsp\n...",
        "pseudocode": "int main(void) { return 0; }",
        "pseudocode_error": None,
        "decompiler": "ghidra",
        "stack_frame": {
            "size": 16,
            "locals": [
                {"name": "local_8", "offset": -8, "size": 4, "type": "int"}
            ],
        },
    })
    assert fn.pseudocode == "int main(void) { return 0; }"
    assert fn.callees[0].is_external is True
    assert fn.stack_frame.size == 16


def test_function_with_null_pseudocode_and_error():
    fn = FunctionSchema.model_validate({
        "address": "0x401000",
        "name": "FUN_00401000",
        "signature": "undefined FUN_00401000(void)",
        "calling_convention": "unknown",
        "size_bytes": 4,
        "is_thunk": False,
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": [],
        "assembly": "",
        "pseudocode": None,
        "pseudocode_error": "Decompile cancelled after 60s",
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    })
    assert fn.pseudocode is None
    assert fn.pseudocode_error is not None


def test_address_must_be_hex_string():
    fn_dict = {
        "address": "401000",  # missing 0x
        "name": "f",
        "signature": "void f(void)",
        "calling_convention": "cdecl",
        "size_bytes": 0,
        "is_thunk": False,
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": [],
        "assembly": "",
        "pseudocode": None,
        "pseudocode_error": None,
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    }
    with pytest.raises(ValidationError):
        FunctionSchema.model_validate(fn_dict)


def test_callref_address_must_be_hex_string():
    ref = CallRefSchema.model_validate({"address": "0x401000", "name": "x"})
    assert ref.address == "0x401000"
    with pytest.raises(ValidationError):
        CallRefSchema.model_validate({"address": "not-hex", "name": "x"})


def test_calling_convention_enum_members():
    # Ensure all spec-listed conventions exist
    expected = {"cdecl", "stdcall", "fastcall", "thiscall", "unknown"}
    actual = {c.value for c in CallingConvention}
    assert expected.issubset(actual)


def test_artifact_to_json_roundtrip():
    original = {
        "schema_version": SCHEMA_VERSION,
        "binary": {
            "path": "/tmp/x.elf",
            "sha256": "ab" * 32,
            "format": "ELF",
            "arch": "x64",
            "endianness": "little",
            "entry_point": "0x400000",
            "base_address": "0x400000",
        },
        "sections": [
            {"name": ".text", "address": "0x401000", "size": 1024, "permissions": "r-x"}
        ],
        "imports": [
            {"address": "0x404000", "name": "puts", "library": "libc.so.6"}
        ],
        "exports": [
            {"address": "0x401000", "name": "main"}
        ],
        "strings": [
            {"address": "0x402000", "value": "hi\n", "encoding": "ascii"}
        ],
        "functions": [],
    }
    artifact = BinaryArtifactSchema.model_validate(original)
    json_str = artifact.model_dump_json()
    restored = BinaryArtifactSchema.model_validate_json(json_str)
    assert restored.binary.path == original["binary"]["path"]
    assert restored.sections[0].name == ".text"
    assert restored.imports[0].name == "puts"
