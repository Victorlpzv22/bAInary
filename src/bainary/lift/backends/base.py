"""Pluggable backend interface for binary lifting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class LifterBackend(ABC):
    """Strategy interface for lifting a binary into the bAInary JSON dict."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for this backend (e.g. 'ghidra_headless')."""

    @abstractmethod
    def lift(self, path: Path, *, timeout_s: int) -> dict[str, Any]:
        """Lift ``path`` and return a dict conforming to the schema.

        Parameters
        ----------
        path
            Path to the binary file.
        timeout_s
            Hard timeout for the entire lift operation, in seconds.

        Returns
        -------
        dict
            The lifted binary, conforming to
            :class:`bainary.lift.schema.BinaryArtifactSchema`.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        LifterError
            If the lifting tool fails, crashes, or times out.
        """

    def ghidra_version(self) -> str | None:
        """If this backend depends on Ghidra, return the detected version.

        Default returns ``None`` (backend doesn't depend on Ghidra).
        The cache uses this to invalidate entries when Ghidra changes.
        """
        return None


class BackendRegistry:
    """Registry of available backends, keyed by name."""

    def __init__(self) -> None:
        self._backends: dict[str, LifterBackend] = {}

    def register(self, backend: LifterBackend) -> None:
        self._backends[backend.name] = backend

    def resolve(self, name: str) -> LifterBackend:
        if name not in self._backends:
            raise KeyError(
                f"unknown backend {name!r}; known: {sorted(self._backends)}"
            )
        return self._backends[name]

    def default_name(self) -> str:
        if not self._backends:
            raise RuntimeError("no backends registered")
        return next(iter(self._backends))
