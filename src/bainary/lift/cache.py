"""sha256-keyed JSON cache for lifted artifacts.

Each cache entry is the validated artifact JSON, with a header field
``_cache_ghidra_version`` that invalidates the entry if the Ghidra
version used to produce it differs from the current one.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from bainary.lift.artifact import BinaryArtifact

log = logging.getLogger(__name__)

_CACHE_HEADER = "_cache_ghidra_version"


class ArtifactCache:
    """A simple, content-addressed cache for lifted artifacts.

    The on-disk layout is::

        <root>/<sha256[0:2]>/<sha256[2:4]>/<sha256>.json

    (sharded to avoid huge directories in the common case where you lift
    many binaries over time).
    """

    def __init__(self, root: Path, *, ghidra_version: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._ghidra_version = ghidra_version

    def _path_for(self, sha256: str) -> Path:
        return self._root / sha256[:2] / sha256[2:4] / f"{sha256}.json"

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

        # Strip the cache header before handing to the artifact constructor
        body = {k: v for k, v in raw.items() if k != _CACHE_HEADER}
        return BinaryArtifact.from_dict(body)

    def store(self, sha256: str, artifact: BinaryArtifact) -> None:
        path = self._path_for(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = artifact.to_dict()
        body[_CACHE_HEADER] = self._ghidra_version
        path.write_text(json.dumps(body, indent=2))

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
