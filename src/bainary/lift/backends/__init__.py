"""Backend registry: imported by the public API to populate available backends."""

from __future__ import annotations

from bainary.lift.backends.base import BackendRegistry

REGISTRY = BackendRegistry()


def default_registry() -> BackendRegistry:
    """Return the registry with default backends registered.

    Safe to call multiple times. Ghidra is registered only if GHIDRA_HOME
    looks valid; the test suite overrides this with a mock.
    """
    if "ghidra_headless" not in REGISTRY._backends:
        try:
            from bainary.lift.backends.ghidra_headless import GhidraHeadlessBackend
            REGISTRY.register(GhidraHeadlessBackend())
        except OSError:
            pass
    return REGISTRY
