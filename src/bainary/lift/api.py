"""Public API for the bAInary lifting subsystem."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bainary.lift.artifact import BinaryArtifact
from bainary.lift.cache import ArtifactCache
from bainary.lift.errors import LifterError

if TYPE_CHECKING:
    from bainary.lift.backends.base import BackendRegistry, LifterBackend

log = logging.getLogger(__name__)

_DEFAULT_CACHE_ROOT = Path(
    os.environ.get("BAINARY_CACHE_DIR", str(Path.home() / ".cache" / "bainary"))
)
_SUPPORTED_FORMATS = {"PE", "ELF"}


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _precheck_with_lief(path: Path) -> None:
    """Cheap format/arch detection via LIEF, before launching a backend.

    Raises :class:`ValueError` if the format or architecture is not in
    the MVP scope (PE/ELF, x86/x64). This avoids a 10-30s Ghidra cold
    start only to fail on an unsupported binary.
    """
    try:
        import lief
    except ImportError as e:
        raise OSError(
            "lief is not installed. Install with: pip install lief"
        ) from e
    try:
        binary = lief.parse(str(path))
    except Exception as e:
        raise ValueError(f"lief could not parse {path}: {e}") from e
    if binary is None:
        raise ValueError(f"lief could not parse {path}")

    fmt = str(getattr(binary, "format", "")).upper()
    if "PE" in fmt:
        fmt = "PE"
    elif "ELF" in fmt:
        fmt = "ELF"
    else:
        raise ValueError(
            f"format {fmt!r} not supported; supported: {sorted(_SUPPORTED_FORMATS)}"
        )
    if fmt not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"format {fmt!r} not supported; supported: {sorted(_SUPPORTED_FORMATS)}"
        )

    machine = _detect_machine(binary)
    if machine == "x64" or machine == "x86":
        return
    if machine is None:
        return
    raise ValueError(
        f"arch {machine!r} not in MVP scope; supported: x86, x64"
    )


def _detect_machine(binary: Any) -> str | None:
    try:
        header = getattr(binary, "header", None)
        if header is None:
            return None
        machine = None
        for attr in ("machine", "machine_type"):
            val = getattr(header, attr, None)
            if val is not None:
                machine = str(val).lower()
                break
        if machine is None:
            return None
        if "amd64" in machine or "x86_64" in machine or "x64" in machine:
            return "x64"
        if "i386" in machine or "i686" in machine or "i486" in machine or "x86" in machine:
            return "x86"
        if "arm" in machine or "aarch" in machine:
            return "arm"
        if "mips" in machine:
            return "mips"
        if "riscv" in machine:
            return "riscv"
        if "none" in machine:
            return None
        return machine
    except Exception:
        return None


def lift(
    path: str | Path,
    *,
    backend: str | None = None,
    backend_instance: LifterBackend | None = None,
    registry: BackendRegistry | None = None,
    use_cache: bool = True,
    cache_dir: Path | None = None,
    ghidra_version: str | None = None,
    timeout_s: int = 600,
) -> BinaryArtifact:
    """Lift a binary into a :class:`BinaryArtifact`."""
    path = Path(path)
    _precheck_with_lief(path)
    sha = _sha256_of(path)

    cache_root = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_ROOT

    if use_cache:
        version = ghidra_version or _detect_version(backend_instance, backend, registry)
        cache = ArtifactCache(cache_root, ghidra_version=version)
        hit = cache.lookup(sha)
        if hit is not None:
            log.info("Cache hit for %s (%s)", path, sha[:8])
            return hit

    chosen = _resolve_backend(backend, backend_instance, registry)
    try:
        artifact_dict = chosen.lift(path, timeout_s=timeout_s)
    except LifterError:
        raise
    except Exception as e:
        raise LifterError(f"backend {chosen.name!r} failed: {e}") from e

    artifact = BinaryArtifact.from_dict(artifact_dict)

    if use_cache:
        version = ghidra_version or _detect_version(backend_instance, backend, registry)
        cache = ArtifactCache(cache_root, ghidra_version=version)
        cache.store(sha, artifact)

    return artifact


def _resolve_backend(
    name: str | None,
    instance: LifterBackend | None,
    registry: BackendRegistry | None,
) -> LifterBackend:
    if instance is not None:
        return instance
    from bainary.lift.backends import default_registry
    reg = registry if registry is not None else default_registry()
    if name is None:
        name = reg.default_name()
    return reg.resolve(name)


def _detect_version(
    instance: LifterBackend | None,
    name: str | None,
    registry: BackendRegistry | None,
) -> str:
    if instance is not None:
        return instance.ghidra_version() or "unknown"
    try:
        backend = _resolve_backend(name, instance, registry)
        return backend.ghidra_version() or "unknown"
    except Exception:
        return "unknown"
