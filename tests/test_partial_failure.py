"""Verify that a partial decompile failure doesn't abort the whole artifact.

The spec requires that when Ghidra fails to decompile ONE function, the
artifact still contains ALL functions, with the failed one marked by
``pseudocode=None`` and a non-null ``pseudocode_error``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from bainary.lift.api import lift
from bainary.lift.backends.base import BackendRegistry, LifterBackend


def _sha() -> str:
    return hashlib.sha256(b"\x7fELF").hexdigest()


def _partial_dict(sha: str) -> dict:
    """An artifact where ONE function decompiled fine and ONE failed."""
    return {
        "schema_version": "1.0",
        "binary": {
            "path": "/tmp/x.elf",
            "sha256": sha,
            "format": "ELF",
            "arch": "x64",
            "endianness": "little",
            "entry_point": "0x400000",
            "base_address": "0x400000",
        },
        "sections": [],
        "imports": [],
        "exports": [],
        "strings": [],
        "functions": [
            {
                "address": "0x401000",
                "name": "good_fn",
                "signature": "void good_fn(void)",
                "calling_convention": "cdecl",
                "size_bytes": 16,
                "is_thunk": False,
                "basic_blocks": [],
                "cfg": {"nodes": [], "edges": []},
                "callers": [],
                "callees": [],
                "assembly": "push rbp\nmov rbp,rsp\nret",
                "pseudocode": "void good_fn(void) {}",
                "pseudocode_error": None,
                "decompiler": "ghidra",
                "stack_frame": {"size": 16, "locals": []},
            },
            {
                "address": "0x401100",
                "name": "bad_fn",
                "signature": "undefined bad_fn(void)",
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
            },
        ],
    }


def test_partial_failure_does_not_abort_artifact(tmp_path):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")

    class _Backend(LifterBackend):
        @property
        def name(self) -> str:
            return "partial"

        def ghidra_version(self) -> str:
            return "v1"

        def lift(self, path: Path, *, timeout_s: int) -> dict[str, Any]:
            return _partial_dict(_sha())

    reg = BackendRegistry()
    reg.register(_Backend())

    artifact = lift(binary, backend="partial", registry=reg, use_cache=False)

    assert len(artifact.functions) == 2
    good = next(f for f in artifact.functions if f.name == "good_fn")
    bad = next(f for f in artifact.functions if f.name == "bad_fn")
    assert good.pseudocode is not None
    assert good.pseudocode_error is None
    assert bad.pseudocode is None
    assert bad.pseudocode_error is not None
    assert "cancelled" in bad.pseudocode_error.lower()
