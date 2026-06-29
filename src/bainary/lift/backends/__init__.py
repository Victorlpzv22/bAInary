"""Backend registry: imported by the public API to populate available backends."""

from __future__ import annotations

from bainary.lift.backends.base import BackendRegistry

REGISTRY = BackendRegistry()


def default_registry() -> BackendRegistry:
    """Return the registry with default backends registered.

    Safe to call multiple times. Backends are registered only if their
    dependencies are available; the test suite overrides this with a mock.
    """
    if "ghidra_headless" not in REGISTRY._backends:
        try:
            from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend

            REGISTRY.register(GhidraHeadlessBackend())
        except OSError:
            pass
    if "lief_capstone" not in REGISTRY._backends:
        try:
            from bainary.lift.backends.lief_capstone import LiefCapstoneBackend

            REGISTRY.register(LiefCapstoneBackend())
        except OSError:
            pass
    return REGISTRY
