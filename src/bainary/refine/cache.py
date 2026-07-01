"""Cache for LLM refinement results.

Keyed by sha256(pseudo_c_original + model + prompt_version).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from bainary.refine.prompts import PROMPT_VERSION

log = logging.getLogger(__name__)


class RefinementCache:
    """File-based cache for refined pseudo-C.

    Each entry is a JSON file at
    ``<root>/<key[0:2]>/<key[2:4]>/<key>.json`` containing the refined
    code and metadata.
    """

    def __init__(
        self,
        root: Path | None = None,
        model: str = "unknown",
    ) -> None:
        if root is None:
            root = Path.home() / ".cache" / "bainary" / "refine"
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._model = model

    def _path_for(self, key: str) -> Path:
        return self._root / key[:2] / key[2:4] / f"{key}.json"

    def lookup(self, key: str) -> str | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Corrupt refine cache entry %s: %s. Deleting.", path, e)
            try:
                path.unlink()
            except OSError:
                pass
            return None

        if raw.get("model") != self._model:
            return None
        if raw.get("prompt_version") != PROMPT_VERSION:
            return None

        refined = raw.get("refined")
        return str(refined) if refined is not None else None

    def store(self, key: str, refined: str) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "key": key,
            "refined": refined,
            "model": self._model,
            "prompt_version": PROMPT_VERSION,
        }
        path.write_text(json.dumps(entry, indent=2))

    def clear(self) -> None:
        if not self._root.exists():
            return
        for f in self._root.rglob("*.json"):
            f.unlink()
        for d in sorted(self._root.rglob("*"), reverse=True):
            if d.is_dir():
                try:
                    d.rmdir()
                except OSError:
                    pass

    def count(self) -> int:
        if not self._root.exists():
            return 0
        return sum(1 for _ in self._root.rglob("*.json"))
