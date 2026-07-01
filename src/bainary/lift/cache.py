"""sha256-keyed JSON cache for lifted artifacts.

Each cache entry is the validated artifact JSON, with a header field
``_cache_ghidra_version`` that invalidates the entry if the Ghidra
version used to produce it differs from the current one.

The cache supports optional LRU eviction: when ``max_entries`` is set,
storing a new entry evicts the least-recently-accessed entries until
the count is within the limit. Access time is tracked via the file's
``mtime`` (updated on every ``lookup`` and ``store``).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from bainary.lift.artifact import BinaryArtifact

log = logging.getLogger(__name__)

_CACHE_HEADER = "_cache_ghidra_version"
_DEFAULT_MAX_ENTRIES = 200


class ArtifactCache:
    """A content-addressed cache for lifted artifacts.

    The on-disk layout is::

        <root>/<sha256[0:2]>/<sha256[2:4]>/<sha256>.json

    Sharded to avoid huge flat directories.

    Parameters
    ----------
    root
        Cache directory.
    ghidra_version
        Current Ghidra version; entries with a different version are
        treated as misses and silently overwritten on next ``store``.
    max_entries
        Soft limit on the number of cached entries. When exceeded,
        least-recently-accessed entries are evicted. ``0`` or ``None``
        disables eviction. Default: 200.
    """

    def __init__(
        self,
        root: Path,
        *,
        ghidra_version: str,
        max_entries: int | None = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._ghidra_version = ghidra_version
        self._max_entries = max_entries or 0

    def _path_for(self, sha256: str) -> Path:
        return self._root / sha256[:2] / sha256[2:4] / f"{sha256}.json"

    def _touch(self, path: Path) -> None:
        """Update mtime to mark this entry as recently accessed."""
        try:
            os.utime(path, None)
        except OSError:
            pass

    def _evict_lru(self) -> None:
        """Evict least-recently-accessed entries until under max_entries."""
        if self._max_entries <= 0:
            return
        entries: list[tuple[float, Path]] = []
        for f in self._root.rglob("*.json"):
            try:
                entries.append((f.stat().st_mtime, f))
            except OSError:
                pass
        if len(entries) <= self._max_entries:
            return
        entries.sort()  # oldest mtime first
        to_evict = len(entries) - self._max_entries
        for _, path in entries[:to_evict]:
            try:
                path.unlink()
                log.debug("Evicted cache entry %s (LRU)", path.name)
            except OSError:
                pass

    def lookup(self, sha256: str) -> BinaryArtifact | None:
        path = self._path_for(sha256)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Corrupt cache entry %s: %s. Deleting.", path, e)
            try:
                path.unlink()
            except OSError:
                pass
            return None

        cached_version = raw.get(_CACHE_HEADER)
        if cached_version != self._ghidra_version:
            log.info(
                "Cache entry %s produced with Ghidra %s, current is %s. Invalidating.",
                sha256,
                cached_version,
                self._ghidra_version,
            )
            return None

        # Mark as recently accessed
        self._touch(path)

        # Strip the cache header before handing to the artifact constructor
        body = {k: v for k, v in raw.items() if k != _CACHE_HEADER}
        return BinaryArtifact.from_dict(body)

    def store(self, sha256: str, artifact: BinaryArtifact) -> None:
        path = self._path_for(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = artifact.to_dict()
        body[_CACHE_HEADER] = self._ghidra_version
        path.write_text(json.dumps(body, indent=2))
        self._touch(path)
        self._evict_lru()

    def clear(self) -> None:
        if not self._root.exists():
            return
        for child in self._root.rglob("*.json"):
            child.unlink()
        # Clean up empty shard dirs
        for child in sorted(self._root.rglob("*"), reverse=True):
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass

    def count(self) -> int:
        """Return the number of cached entries."""
        if not self._root.exists():
            return 0
        return sum(1 for _ in self._root.rglob("*.json"))
