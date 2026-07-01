"""Ghidra headless backend: spawns ``analyzeHeadless`` per binary."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from bainary.lift.backends.base import LifterBackend
from bainary.lift.backends.postscript import POSTSCRIPT_SOURCE
from bainary.lift.errors import LifterError

log = logging.getLogger(__name__)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_ghidra_version(ghidra_home: Path) -> str:
    # application.properties lives at $GHIDRA_HOME/Ghidra/application.properties
    # in current Ghidra versions (11.x).
    props = ghidra_home / "Ghidra" / "application.properties"
    if not props.exists():
        raise OSError(
            f"Cannot find Ghidra application.properties at {props}. "
            f"Set GHIDRA_HOME to your Ghidra installation directory."
        )
    for line in props.read_text().splitlines():
        if line.startswith("application.version="):
            return line.split("=", 1)[1].strip()
    raise OSError(f"Could not parse application.version from {props}")


class GhidraHeadlessBackend(LifterBackend):
    """The default backend. Spawns ``analyzeHeadless`` per binary.

    Cold-start per binary is 10-30s; this is mitigated by the
    sha256-keyed cache in :mod:`bainary.lift.cache`.
    """

    def __init__(self, ghidra_home: Path | None = None) -> None:
        if ghidra_home is None:
            env = os.environ.get("GHIDRA_HOME")
            if not env:
                raise OSError(
                    "GHIDRA_HOME is not set. Install Ghidra and set GHIDRA_HOME "
                    "to the Ghidra installation directory."
                )
            ghidra_home = Path(env)
        self._ghidra_home: Path = ghidra_home

    @property
    def name(self) -> str:
        return "ghidra_headless"

    def ghidra_version(self) -> str:
        return _read_ghidra_version(self._ghidra_home)

    def _analyze_headless_path(self) -> Path:
        # analyzeHeadless lives at $GHIDRA_HOME/support/analyzeHeadless on
        # Linux/macOS, or $GHIDRA_HOME/support/analyzeHeadless.bat on Windows.
        if os.name == "nt":
            return self._ghidra_home / "support" / "analyzeHeadless.bat"
        return self._ghidra_home / "support" / "analyzeHeadless"

    def lift(self, path: Path, *, timeout_s: int) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)

        sha = _sha256_of(path)
        version = self.ghidra_version()
        ah = self._analyze_headless_path()

        with tempfile.TemporaryDirectory(prefix="bainary_") as workdir:
            work = Path(workdir)
            project_dir = work / "proj"
            project_dir.mkdir()
            post_script = work / "dump.py"
            post_script.write_text(POSTSCRIPT_SOURCE)
            out_json = work / "out.json"

            cmd = [
                str(ah),
                str(project_dir),
                "bainary_proj",
                "-import",
                str(path),
                "-postScript",
                str(post_script),
                "-postScriptArgs",
                str(out_json),
                "-deleteproject",
            ]
            log.info("Running: %s", " ".join(cmd))
            try:
                proc = subprocess.run(
                    cmd,
                    timeout=timeout_s,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "BAINARY_OUTPUT_JSON": str(out_json)},
                )
            except subprocess.TimeoutExpired as e:
                raise LifterError(
                    f"analyzeHeadless timed out after {timeout_s}s",
                    stderr=(e.stderr.decode(errors="replace") if e.stderr else ""),
                ) from e

            if proc.returncode != 0:
                raise LifterError(
                    f"analyzeHeadless exited with {proc.returncode}",
                    stderr=proc.stderr,
                    returncode=proc.returncode,
                )

            if not out_json.exists():
                raise LifterError(
                    f"analyzeHeadless did not produce {out_json}. stderr:\n{proc.stderr}"
                )

            if proc.stderr:
                log.debug("Ghidra stderr:\n%s", proc.stderr)
            if proc.stdout:
                log.debug("Ghidra stdout:\n%s", proc.stdout)

            raw: dict[str, Any] = json.loads(out_json.read_text())

        raw.setdefault("binary", {})["sha256"] = sha
        raw["binary"]["decompiler_version"] = f"ghidra-{version}"
        raw["binary"]["path"] = str(path.resolve())

        # Normalize calling_convention to the schema's enum. Ghidra reports
        # values like "__stdcall", "processEntry", "unknown" that we map
        # to the closest enum member.
        for func in raw.get("functions", []):
            cc = func.get("calling_convention")
            if cc is not None:
                cc_norm = _normalize_calling_convention(cc)
                func["calling_convention"] = cc_norm

            # Ghidra's iteration order over callers/callees is not stable
            # across runs (it depends on internal hash ordering). Sort by
            # (address, name) for deterministic snapshots.
            for key in ("callers", "callees"):
                items = func.get(key)
                if isinstance(items, list):
                    func[key] = sorted(
                        items,
                        key=lambda x: (x.get("address", ""), x.get("name", "")),
                    )

        return raw


def _normalize_calling_convention(cc: str) -> str:
    """Map Ghidra's calling-convention strings to the schema's enum."""
    s = cc.strip().lower()
    if s in {"cdecl", "stdcall", "fastcall", "thiscall", "unknown"}:
        return s
    if "stdcall" in s:
        return "stdcall"
    if "cdecl" in s:
        return "cdecl"
    if "fastcall" in s:
        return "fastcall"
    if "thiscall" in s:
        return "thiscall"
    return "unknown"
