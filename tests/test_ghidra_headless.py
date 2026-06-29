"""Integration tests that require a real Ghidra installation.

Marked @pytest.mark.slow. Skipped by default with `pytest -m 'not slow'`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bainary.lift.api import lift

GHIDRA_HOME = Path(os.environ.get("GHIDRA_HOME", ""))
FIX = Path(__file__).resolve().parent / "fixtures"


pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def ghidra_home() -> Path:
    if not str(GHIDRA_HOME) or not GHIDRA_HOME.exists():
        pytest.skip("GHIDRA_HOME not set or missing")
    # Sanity check: must contain a Ghidra installation with application.properties
    if not (GHIDRA_HOME / "Ghidra" / "Features" / "Base" / "application.properties").exists():
        pytest.skip(f"GHIDRA_HOME ({GHIDRA_HOME}) is not a valid Ghidra install")
    return GHIDRA_HOME


@pytest.mark.parametrize("fixture_name,expected_format", [
    ("hello_elf64/hello.elf", "ELF"),
    ("loops_elf64/loops.elf", "ELF"),
    ("callchain_elf64/callchain.elf", "ELF"),
])
def test_lift_real_elf(ghidra_home, fixture_name, expected_format):
    binary = FIX / fixture_name
    if not binary.exists():
        pytest.skip(f"fixture {binary} not built; run scripts/gen_fixtures.py")
    artifact = lift(binary, use_cache=False, timeout_s=300)
    assert artifact.binary.format == expected_format
    assert artifact.binary.arch == "x64"
    assert len(artifact.functions) >= 1
    at_least_one_pseudocode = any(f.pseudocode for f in artifact.functions)
    assert at_least_one_pseudocode, "expected at least one function with non-null pseudocode"


def test_lift_callchain_has_depth(ghidra_home):
    binary = FIX / "callchain_elf64" / "callchain.elf"
    if not binary.exists():
        pytest.skip("fixture not built")
    artifact = lift(binary, use_cache=False, timeout_s=300)
    a = next((f for f in artifact.functions if f.name == "a"), None)
    assert a is not None
    assert any(c.name == "b" for c in a.callees)
    b = next(f for f in artifact.functions if f.name == "b")
    assert any(c.name == "c" for c in b.callees)
