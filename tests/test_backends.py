import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bainary.lift.backends.base import BackendRegistry, LifterBackend


def test_backend_registry_has_at_least_one_backend():
    from bainary.lift.backends import default_registry
    reg = default_registry()
    if not reg._backends:  # type: ignore[attr-defined]
        pytest.skip("No backends installed")
    # Ghidra is the preferred default; lief_capstone is the fallback
    assert reg.default_name() in ("ghidra_headless", "lief_capstone")


def test_backend_registry_resolve_known_backend():
    from bainary.lift.backends import default_registry
    reg = default_registry()
    if "ghidra_headless" not in reg._backends:  # type: ignore[attr-defined]
        if "lief_capstone" in reg._backends:  # type: ignore[attr-defined]
            backend = reg.resolve("lief_capstone")
            assert backend.name == "lief_capstone"
            return
        pytest.skip("No backends installed")
    backend = reg.resolve("ghidra_headless")
    assert backend.name == "ghidra_headless"


def test_backend_registry_resolve_unknown_raises():
    reg = BackendRegistry()
    with pytest.raises(KeyError):
        reg.resolve("nope")


def test_backend_registry_register_custom():
    reg = BackendRegistry()

    class FakeBackend(LifterBackend):
        @property
        def name(self) -> str:
            return "fake"

        def lift(self, path: Path, *, timeout_s: int) -> dict[str, Any]:
            return {}

    reg.register(FakeBackend())
    assert reg.resolve("fake").name == "fake"


def test_lifter_backend_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LifterBackend()  # type: ignore[abstract]


def test_ghidra_backend_name():
    from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend
    b = GhidraHeadlessBackend(ghidra_home=Path("/opt/ghidra"))
    assert b.name == "ghidra_headless"


def test_ghidra_backend_ghidra_version_reads_application_properties(tmp_path):
    from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend
    ghidra_home = tmp_path / "ghidra"
    ghidra_props = ghidra_home / "Ghidra"
    ghidra_props.mkdir(parents=True)
    (ghidra_props / "application.properties").write_text(
        "application.name=Ghidra\napplication.version=11.0.1\n"
    )
    b = GhidraHeadlessBackend(ghidra_home=ghidra_home)
    assert b.ghidra_version() == "11.0.1"


def test_ghidra_backend_ghidra_version_missing_raises(tmp_path):
    from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend
    b = GhidraHeadlessBackend(ghidra_home=tmp_path / "nope")
    with pytest.raises((EnvironmentError, FileNotFoundError)):
        b.ghidra_version()


def test_ghidra_backend_lift_invokes_subprocess(tmp_path, monkeypatch):
    from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend
    ghidra_home = tmp_path / "ghidra"
    props_dir = ghidra_home / "Ghidra"
    props_dir.mkdir(parents=True)
    (props_dir / "application.properties").write_text("application.version=11.0.1\n")

    binary = tmp_path / "target.elf"
    binary.write_bytes(b"\x7fELF...")

    captured = {}

    def fake_run(*args, **kwargs):
        cmd_list = args[0] if args else kwargs.get("args", [])
        captured["cmd"] = cmd_list
        captured["kwargs"] = kwargs
        for i, tok in enumerate(cmd_list):
            if tok == "-postScriptArgs" and i + 1 < len(cmd_list):
                out_path = cmd_list[i + 1]
                Path(out_path).write_text(json.dumps({
                    "schema_version": "1.0",
                    "binary": {
                        "path": str(binary), "sha256": "ab" * 32,
                        "format": "ELF", "arch": "x64", "endianness": "little",
                        "entry_point": "0x400000", "base_address": "0x400000",
                    },
                    "sections": [], "imports": [], "exports": [], "strings": [],
                    "functions": [],
                }))
                break
        result = MagicMock()
        result.returncode = 0
        result.stdout = "INFO ...\n"
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)

    b = GhidraHeadlessBackend(ghidra_home=ghidra_home)
    artifact_dict = b.lift(binary, timeout_s=60)

    assert artifact_dict["binary"]["format"] == "ELF"
    assert "analyzeHeadless" in " ".join(captured["cmd"])
    assert len(artifact_dict["binary"]["sha256"]) == 64
    assert artifact_dict["binary"]["decompiler_version"] == "ghidra-11.0.1"
