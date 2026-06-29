"""Compile tests/fixtures/*.c to ELF and PE binaries.

Usage:
    python scripts/gen_fixtures.py

Requires:
    - gcc (for ELF)
    - mingw-w64 (for PE): e.g. apt install gcc-mingw-w64-x86-64
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"

ELF_CC = "gcc"
PE_CC = "x86_64-w64-mingw32-gcc"

SOURCES = ["hello.c", "loops.c", "callchain.c"]


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def main() -> int:
    failures = 0

    for src_name in SOURCES:
        stem = src_name.replace(".c", "")
        c_src = FIX / src_name
        if not c_src.exists():
            print(f"  ! missing source: {c_src}", file=sys.stderr)
            failures += 1
            continue

        if _have(ELF_CC):
            out = FIX / f"{stem}_elf64" / f"{stem}.elf"
            out.parent.mkdir(exist_ok=True)
            print(f"  gcc {src_name}  ->  {out.relative_to(ROOT)}")
            r = subprocess.run(
                [ELF_CC, str(c_src), "-O0", "-g", "-o", str(out), "-no-pie"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"    gcc failed:\n{r.stderr}", file=sys.stderr)
                failures += 1
        else:
            print("  ! gcc not found; skipping ELF builds")

        if _have(PE_CC):
            out = FIX / f"{stem}_pe64" / f"{stem}.exe"
            out.parent.mkdir(exist_ok=True)
            print(f"  mingw {src_name}  ->  {out.relative_to(ROOT)}")
            r = subprocess.run(
                [PE_CC, str(c_src), "-O0", "-g", "-o", str(out)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"    mingw failed:\n{r.stderr}", file=sys.stderr)
                failures += 1
        else:
            print("  ! mingw not found; skipping PE builds")

    if failures:
        print(f"\n{failures} failure(s).", file=sys.stderr)
        return 1
    print("\nAll fixtures generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
