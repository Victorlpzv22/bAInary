import json

import pytest

from bainary.lift.artifact import (
    BasicBlock,  # noqa: F401
    BinaryArtifact,
    BinaryInfo,  # noqa: F401
    CallRef,  # noqa: F401
    ExportRef,  # noqa: F401
    Function,
    ImportRef,  # noqa: F401
    Instruction,  # noqa: F401
    Local,  # noqa: F401
    Section,  # noqa: F401
    StackFrame,  # noqa: F401
    StringRef,  # noqa: F401
)


def _minimal_dict() -> dict:
    return {
        "schema_version": "1.0",
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
        "imports": [],
        "exports": [{"address": "0x401000", "name": "main"}],
        "strings": [],
        "functions": [
            {
                "address": "0x401000",
                "name": "main",
                "signature": "int main(void)",
                "calling_convention": "cdecl",
                "size_bytes": 16,
                "is_thunk": False,
                "basic_blocks": [
                    {
                        "address": "0x401000",
                        "instructions": [
                            {
                                "address": "0x401000",
                                "bytes": "55",
                                "mnemonic": "push",
                                "operands": ["rbp"],
                                "comment": None,
                            }
                        ],
                        "successors": ["0x401001"],
                        "terminator": "fall_through",
                    }
                ],
                "cfg": {
                    "nodes": ["0x401000", "0x401001"],
                    "edges": [["0x401000", "0x401001"]],
                },
                "callers": [],
                "callees": [],
                "assembly": "push rbp\nmov rbp,rsp\nret",
                "pseudocode": "int main(void) { return 0; }",
                "pseudocode_error": None,
                "decompiler": "ghidra",
                "stack_frame": {"size": 16, "locals": []},
            }
        ],
    }


def test_artifact_from_dict():
    artifact = BinaryArtifact.from_dict(_minimal_dict())
    assert artifact.binary.format == "ELF"
    assert artifact.binary.arch == "x64"
    assert len(artifact.functions) == 1
    fn = artifact.functions[0]
    assert fn.pseudocode == "int main(void) { return 0; }"
    assert len(fn.basic_blocks) == 1
    assert fn.basic_blocks[0].instructions[0].mnemonic == "push"


def test_artifact_to_json_from_json_roundtrip(tmp_path):
    artifact = BinaryArtifact.from_dict(_minimal_dict())
    path = tmp_path / "out.json"
    artifact.to_json(path)
    restored = BinaryArtifact.from_json(path)
    assert restored.binary.sha256 == artifact.binary.sha256
    assert restored.functions[0].address == artifact.functions[0].address
    assert restored.functions[0].pseudocode == artifact.functions[0].pseudocode


def test_artifact_to_dict_is_serializable():
    artifact = BinaryArtifact.from_dict(_minimal_dict())
    d = artifact.to_dict()
    json.dumps(d)


def test_artifact_from_invalid_dict_raises_schema_error():
    from bainary.lift.errors import SchemaValidationError

    bad = _minimal_dict()
    del bad["binary"]["format"]
    with pytest.raises(SchemaValidationError):
        BinaryArtifact.from_dict(bad)


def test_artifact_handles_null_pseudocode():
    d = _minimal_dict()
    d["functions"][0]["pseudocode"] = None
    d["functions"][0]["pseudocode_error"] = "Decompile cancelled"
    artifact = BinaryArtifact.from_dict(d)
    assert artifact.functions[0].pseudocode is None
    assert artifact.functions[0].pseudocode_error == "Decompile cancelled"


def test_function_dataclass_construction():
    fn = Function(
        address="0x401000",
        name="f",
        signature="void f(void)",
        calling_convention="cdecl",
        size_bytes=0,
        assembly="",
    )
    assert fn.pseudocode is None
    assert fn.pseudocode_error is None
    assert fn.is_thunk is False
    assert fn.cfg.nodes == []
