from pathlib import Path
from typing import Any

import pytest

from bainary.lift.backends.base import BackendRegistry, LifterBackend


@pytest.mark.skip(reason="requires ghidra backend registration; added in Task 8")
def test_backend_registry_default_is_ghidra_headless():
    reg = BackendRegistry()
    assert reg.default_name() == "ghidra_headless"


@pytest.mark.skip(reason="requires ghidra backend registration; added in Task 8")
def test_backend_registry_resolve_known_backend():
    reg = BackendRegistry()
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
