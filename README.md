# bAInary

AI-assisted reverse engineering of compiled binaries.

## What's done

- **Subsystem A — Binary parsing & lifting** (`bainary.lift`). Lift PE / ELF / Mach-O binaries (x86, x64, ARM, ARM64) to a structured JSON artifact with every function, its ASM, Ghidra's pseudo-C, control flow graph, callers/callees, sections, imports, exports, and strings. Two backends: `ghidra_headless` (with decompilation, 10–30s) and `lief_capstone` (ASM only, <1s).
- **Subsystem B — Call graph** (`bainary.graph`). Build a `networkx.DiGraph` from any `BinaryArtifact`. Query callers, callees (direct or transitive), orphans, cycles (SCCs), and shortest paths. Serialize to GraphML (interchange) or pickle (lossless). Hybrid API: ergonomic methods + raw `cg.graph` access.
- **Subsystem D — LLM refinement (PoC)** (`scripts/poc_llm.py`). Send the smallest functions of a binary to an LLM and get back cleaned-up pseudo-C with meaningful variable names and comments. Validated end-to-end with OpenCode Go (Kimi K2.7 Code model). This is a proof-of-concept script, not a library — the real `D` subsystem (with batch processing, cache, tests) is still future work.

## What's not done yet

- **C — RAG / embeddings.** Index functions semantically and search for similar ones across a corpus. Requires a vector store and an embeddings model.
- **D — full subsystem.** The PoC works, but the real `bainary.refine` package (refiner class, batch + parallel processing, refinement cache, smart function selection, mocked tests) hasn't been designed or built.
- **E — GUI.** Side-by-side Hex/ASM vs. reconstructed code view.

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
- **Java 21+** (required by Ghidra 11.3+)
- **Ghidra 11.x** — [download from the NSA](https://ghidra-sre.org/). After installing, point `GHIDRA_HOME` at the install directory:
  ```bash
  export GHIDRA_HOME=/opt/ghidra_11.3.2_PUBLIC
  ```
  (Put this in your shell rc or `.env`.)
- The `lief_capstone` backend works without Ghidra (for fast ASM-only lifting). The `ghidra_headless` backend requires Ghidra + Java.

## CLI usage

```bash
bainary-lift path/to/target.exe -o target.json
bainary-lift path/to/target.elf -o target.json --no-cache       # force re-lift
bainary-lift path/to/target.elf -o target.json --timeout 900     # custom Ghidra timeout
bainary-lift path/to/target.elf -o target.json --verbose -v     # debug logging

# Use the fast backend (no Ghidra needed, no pseudo-C):
bainary-lift path/to/target.elf -o target.json --backend lief_capstone
```

## Library usage

### Subsystem A — lift a binary

```python
from bainary.lift import lift

artifact = lift("target.exe")  # uses ghidra_headless by default
print(artifact.binary.decompiler_version)  # e.g. "ghidra-11.3.2"
for fn in artifact.functions:
    print(fn.address, fn.name)
    print("  ASM:")
    print(fn.assembly)
    print("  Pseudo-C:")
    print(fn.pseudocode)
    print(f"  calls: {[c.name for c in fn.callees]}")
```

### Subsystem B — call graph

```python
from bainary.graph import CallGraph

cg = CallGraph.from_artifact(artifact)  # or CallGraph.from_json("target.json")

# Common queries
print("Orphans:", cg.orphans())                   # nobody calls them
print("Cycles:", cg.cycles())                     # SCCs with > 1 node
print("main → c:", cg.shortest_path("main", "c"))  # or None
print("callees of main:", cg.callees_of("main"))
print("transitive callers of printf:", cg.callers_of("printf", transitive=True))

# Raw NetworkX graph for advanced queries
import networkx as nx
bc = nx.betweenness_centrality(cg.graph)
for addr, val in sorted(bc.items(), key=lambda x: -x[1])[:3]:
    print(f"  {cg.functions[addr].name}: {val:.3f}")

# Serialize
cg.to_graphml("callgraph.graphml")
cg.to_pickle("callgraph.pkl")
```

### Subsystem D — LLM refinement (PoC)

```bash
export OPENCODE_APIKEY='sk-...'  # your OpenCode Go key
python scripts/poc_llm.py path/to/target.elf
```

Picks the N smallest functions (default 3), sends each to the LLM, and prints original and refined side-by-side. Defaults to model `kimi-k2.7-code` — override with `--model`.

## Building test fixtures

```bash
python scripts/gen_fixtures.py
```

Compiles `tests/fixtures/*.c` to ELF (via `gcc`) and PE (via `x86_64-w64-mingw32-gcc`). The compiled binaries **are committed** so that snapshot tests are stable across machines and gcc versions. If you change a `.c` source, re-run the generator and commit the new binaries.

## Running tests

```bash
# Fast lane (no Ghidra required)
pytest -m "not slow"

# Full suite (requires GHIDRA_HOME)
pytest

# Regenerate snapshot golden files after an intentional change
pytest tests/test_snapshot.py --update-snapshots -m slow
```

73 tests pass in the fast lane. 7 more (integration + snapshot) run when Ghidra is available.

## Cache

Lifted artifacts are cached at `$BAINARY_CACHE_DIR` (defaults to `~/.cache/bainary/`) keyed by the binary's sha256. The layout is sharded (`<root>/<sha[0:2]>/<sha[2:4]>/<sha>.json`) to avoid huge flat directories. Cache entries are invalidated automatically when the Ghidra version changes. Pass `--no-cache` (CLI) or `use_cache=False` (library) to bypass. The cache is LRU-evicted at 200 entries by default.

```bash
export BAINARY_CACHE_DIR=/tmp/bainary-cache  # override cache location
```

## License

MIT
