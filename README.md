# bAInary

AI-assisted reverse engineering of compiled binaries.

> Status: **subsystem A (binary parsing & lifting) MVP**. The full design
> is in `docs/superpowers/specs/2026-06-29-lift-subsystem-design.md`
> (ignored by git; consult it on disk for the spec).

## What this does (today)

Takes a PE or ELF binary (x86 or x64) and lifts it to a structured JSON
artifact with every function, its assembly, Ghidra's pseudo-C, control
flow graph, callers/callees, sections, imports, exports, and strings.

That's it for the MVP. Future subsystems will:

- **B** — build a call graph and propagate inferred types.
- **C** — embed functions for RAG-based similarity search.
- **D** — use an LLM to clean up Ghidra's pseudo-C, rename symbols, summarize functions.
- **E** — provide a GUI with a side-by-side Hex/ASM vs. reconstructed code view.

## Install

```bash
git clone <repo> bainary
cd bainary
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Requirements

- **Python 3.11+**
- **Java 17+** (required by Ghidra)
- **Ghidra 11.x** — [download from the NSA](https://ghidra-sre.org/). After installing, point `GHIDRA_HOME` at the install directory:
  ```bash
  export GHIDRA_HOME=/opt/ghidra_11.0.1_PUBLIC
  ```
  (Put this in your shell rc or `.env`.)

## CLI usage

```bash
bainary-lift path/to/target.exe -o target.json
bainary-lift path/to/target.elf -o target.json --no-cache  # force re-lift
bainary-lift path/to/target.elf -o target.json --timeout 900
bainary-lift path/to/target.elf -o target.json --verbose    # debug logging
```

The output is JSON conforming to the schema documented in the design spec.

## Library usage

```python
from bainary.lift import lift

artifact = lift("target.exe")
print(artifact.binary.decompiler_version)  # e.g. "ghidra-11.0.1"
for fn in artifact.functions:
    print(fn.address, fn.name)
    print("ASM:")
    print(fn.assembly)
    print("Pseudo-C:")
    print(fn.pseudocode)
    print(f"  calls: {[c.name for c in fn.callees]}")
```

## Building test fixtures

```bash
python scripts/gen_fixtures.py
```

This compiles `tests/fixtures/*.c` to ELF (via `gcc`) and PE (via
`x86_64-w64-mingw32-gcc`). The compiled binaries **are committed** so
that snapshot tests are stable across machines and gcc versions. If you
change a `.c` source, re-run the generator and commit the new binaries.

## Running tests

```bash
# Fast lane (no Ghidra required)
pytest -m "not slow"

# Full suite (requires GHIDRA_HOME)
pytest

# Regenerate snapshot golden files after an intentional change
pytest tests/test_snapshot.py --update-snapshots -m slow
```

## Cache

Lifted artifacts are cached at `$BAINARY_CACHE_DIR` (defaults to
`~/.cache/bainary/`) keyed by the binary's sha256. The layout is sharded
(`<root>/<sha[0:2]>/<sha[2:4]>/<sha>.json`) to avoid huge flat
directories. Cache entries are invalidated automatically when the Ghidra
version changes. Pass `--no-cache` (CLI) or `use_cache=False` (library)
to bypass.

```bash
export BAINARY_CACHE_DIR=/tmp/bainary-cache  # override cache location
```

## Architecture

See the design spec at
`docs/superpowers/specs/2026-06-29-lift-subsystem-design.md` for the
full architecture, data flow, error handling, and testing strategy.

## License

MIT
