import hashlib
from pathlib import Path
from typing import Any

import pytest

from bainary.lift.api import lift
from bainary.lift.artifact import BinaryArtifact
from bainary.lift.backends.base import LifterBackend
from bainary.lift.errors import LifterError, SchemaValidationError


def _sample_dict(sha: str) -> dict:
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
        "sections": [], "imports": [], "exports": [], "strings": [], "functions": [],
    }


class FakeBackend(LifterBackend):
    def __init__(self, return_dict: dict | None = None, raise_exc: Exception | None = None,
                 call_log: list | None = None) -> None:
        self._return = return_dict or _sample_dict("ab" * 32)
        self._raise = raise_exc
        self._log = call_log if call_log is not None else []

    @property
    def name(self) -> str:
        return "fake"

    def ghidra_version(self) -> str | None:
        return "fake-1.0"

    def lift(self, path: Path, *, timeout_s: int) -> dict[str, Any]:
        self._log.append(path)
        if self._raise is not None:
            raise self._raise
        return self._return


def test_lift_returns_artifact(tmp_path):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    sha = hashlib.sha256(b"\x7fELF").hexdigest()

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(FakeBackend(return_dict=_sample_dict(sha)))

    artifact = lift(binary, backend="fake", registry=reg, use_cache=False)
    assert isinstance(artifact, BinaryArtifact)
    assert artifact.binary.sha256 == sha


def test_lift_caches_result(tmp_path, tmp_cache_dir):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    sha = hashlib.sha256(b"\x7fELF").hexdigest()
    log: list = []
    backend = FakeBackend(return_dict=_sample_dict(sha), call_log=log)

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(backend)

    a1 = lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-1.0")
    a2 = lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-1.0")
    assert a1.binary.sha256 == a2.binary.sha256
    assert len(log) == 1


def test_lift_cache_miss_increments_backend_call(tmp_path, tmp_cache_dir):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    sha = hashlib.sha256(b"\x7fELF").hexdigest()
    log: list = []
    backend = FakeBackend(return_dict=_sample_dict(sha), call_log=log)

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(backend)

    a1 = lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-1.0")
    a2 = lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-2.0")
    assert a1.binary.sha256 == a2.binary.sha256
    assert len(log) == 2


def test_lift_use_cache_false_skips_cache(tmp_path, tmp_cache_dir):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    sha = hashlib.sha256(b"\x7fELF").hexdigest()
    log: list = []
    backend = FakeBackend(return_dict=_sample_dict(sha), call_log=log)

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(backend)

    lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-1.0", use_cache=False)
    lift(binary, backend="fake", registry=reg, cache_dir=tmp_cache_dir, ghidra_version="fake-1.0", use_cache=False)
    assert len(log) == 2


def test_lift_wraps_backend_exception_in_lifter_error(tmp_path):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(FakeBackend(raise_exc=RuntimeError("boom")))

    with pytest.raises(LifterError) as excinfo:
        lift(binary, backend="fake", registry=reg, use_cache=False)
    assert "boom" in str(excinfo.value)


def test_lift_rejects_unsupported_format_via_lief(tmp_path):
    binary = tmp_path / "x.macho"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 20)
    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(FakeBackend())

    with pytest.raises(ValueError, match="format"):
        lift(binary, backend="fake", registry=reg, use_cache=False)


def test_lift_rejects_unsupported_arch(tmp_path):
    import struct
    e_ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
    e_type = struct.pack("<H", 2)
    e_machine = struct.pack("<H", 0x28)
    e_version = struct.pack("<I", 1)
    header = e_ident + e_type + e_machine + e_version + b"\x00" * 40
    binary = tmp_path / "x.arm.elf"
    binary.write_bytes(header)

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(FakeBackend())

    with pytest.raises(ValueError, match="arch"):
        lift(binary, backend="fake", registry=reg, use_cache=False)


def test_lift_validates_schema_after_backend(tmp_path):
    binary = tmp_path / "x.elf"
    binary.write_bytes(b"\x7fELF")
    bad_dict = {"this is not": "a valid artifact"}

    from bainary.lift.backends.base import BackendRegistry
    reg = BackendRegistry()
    reg.register(FakeBackend(return_dict=bad_dict))

    with pytest.raises(SchemaValidationError):
        lift(binary, backend="fake", registry=reg, use_cache=False)
