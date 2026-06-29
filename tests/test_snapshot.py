"""Snapshot tests: compare lift() output against committed golden files.

Marked @pytest.mark.slow because they require a real Ghidra install.

To regenerate golden files after an intentional change (e.g. a new
Ghidra version, a schema bump):

    pytest tests/test_snapshot.py --update-snapshots -m slow

Then review the diff and commit the updated files.
"""

from __future__ import annotations

import json
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
    if not (GHIDRA_HOME / "Ghidra" / "Features" / "Base" / "application.properties").exists():
        pytest.skip(f"GHIDRA_HOME ({GHIDRA_HOME}) is not a valid Ghidra install")
    return GHIDRA_HOME


def _fixture_paths() -> list[Path]:
    out = []
    for stem in ("hello", "loops", "callchain"):
        p = FIX / f"{stem}_elf64" / f"{stem}.elf"
        if p.exists():
            out.append(p)
    return out


@pytest.mark.parametrize("fixture", _fixture_paths(), ids=lambda p: p.stem)
def test_snapshot_matches_golden(ghidra_home, fixture, snapshot_dir, update_snapshots):
    artifact = lift(fixture, use_cache=False, timeout_s=300)
    actual = json.loads(artifact.to_json_str())
    golden = snapshot_dir / f"{fixture.stem}.json"

    if update_snapshots or not golden.exists():
        golden.write_text(json.dumps(actual, indent=2, sort_keys=True))
        pytest.skip(f"snapshot written to {golden}; review and commit")

    expected = json.loads(golden.read_text())
    assert actual == expected, (
        f"Snapshot mismatch for {fixture.name}.\n"
        f"Golden: {golden}\n"
        f"Run: pytest tests/test_snapshot.py --update-snapshots -m slow\n"
        f"Then review the diff and commit if the change is intentional."
    )
