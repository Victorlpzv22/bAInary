# bAInary

AI-assisted reverse engineering of compiled binaries.

## What's done

- **Subsystem A — Binary parsing & lifting** (`bainary.lift`). Lift PE / ELF / Mach-O binaries (x86, x64, ARM, ARM64) to a structured JSON artifact with every function, its ASM, Ghidra's pseudo-C, control flow graph, callers/callees, sections, imports, exports, and strings. Two backends: `ghidra_headless` (with decompilation, 10–30s) and `lief_capstone` (ASM only, <1s). Sha256-keyed cache with LRU eviction.
- **Subsystem B — Call graph** (`bainary.graph`). Build a `networkx.DiGraph` from any `BinaryArtifact`. Query callers, callees (direct or transitive), orphans, cycles (SCCs), and shortest paths. Serialize to GraphML (interchange) or pickle (lossless). Hybrid API: ergonomic methods + raw `cg.graph` access.
- **Subsystem D — LLM refinement** (`bainary.refine`). Send decompiled pseudo-C to an LLM and get back cleaned-up code with meaningful variable names, removed warnings, and one-line comments. Multi-provider: OpenAI, Anthropic, OpenCode Go (GLM-5.2, Kimi K2.7 Code, DeepSeek V4, MiniMax M3, etc.). Cache prevents duplicate LLM calls. Filters for thunks, empty functions, and size. A `bainary-refine` package, not just a script.
- **Subsystem C — Cross-binary function search** (`bainary.rag`). Index every function in a `BinaryArtifact` and search for similar functions across a multi-binary corpus. Vectorization is local (hashing trick over n-gram tokens, no model, no API key, no network) and pluggable via `TextualVectorizer`. Pluggable vector store (NumPy + JSON MVP, ChromaDB/LanceDB/sqlite-vec/FAISS future). Pseudocode-first text with ASM fallback.
- **Subsystem E — Web GUI** (`bainary.gui`, optional `pip install '.[gui]'`). Local web app at `127.0.0.1:8787` driven by `bainary-gui`. Monaco editor for ASM + pseudo-C (Original / Refinado / Diff), vis-network for the call graph, SSE for live lift/refine progress, and a RAG search panel — all behind a single `ArtifactSession`. Subsystems A, B, C, D are exposed as a JSON REST API under `/api/*`.

## Install

```bash
git clone <repo> bainary
cd bainary
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # CLI + tests
pip install -e ".[gui]"          # optional: web GUI (bainary-gui)
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
- For subsystem D, an LLM API key (OpenCode Go, OpenAI, or Anthropic).

## CLI usage

```bash
bainary-lift path/to/target.exe -o target.json
bainary-lift path/to/target.elf -o target.json --no-cache       # force re-lift
bainary-lift path/to/target.elf -o target.json --timeout 900     # custom Ghidra timeout
bainary-lift path/to/target.elf -o target.json --verbose -v     # debug logging

# Use the fast backend (no Ghidra needed, no pseudo-C):
bainary-lift path/to/target.elf -o target.json --backend lief_capstone

# Web GUI (subsystem E)
bainary-gui                                       # opens http://127.0.0.1:8787
bainary-gui --port 9000 --no-browser              # headless / custom port
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

### Subsystem D — LLM refinement

```python
import os
from bainary.refine import Refiner, create_client

client = create_client(
    provider="openai",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="kimi-k2.7-code",
)

refiner = Refiner(client=client)
refined = refiner.refine(artifact, cg)  # returns a NEW BinaryArtifact

# Original is untouched; refined has clean pseudo-C
main = next(f for f in refined.functions if f.name == "main")
print(main.pseudocode)
```

Supports OpenAI, Anthropic, and Mock (for tests) providers. Filters: `min_size`, `skip_thunks`, `skip_no_pseudocode`. Cache automatic.

### Subsystem C — Cross-binary function search

```python
from bainary.rag import Index, create_textual_vectorizer

vec = create_textual_vectorizer()        # default: HashingTextVectorizer(dim=1024)
idx = Index(vectorizer=vec)              # defaults to NumpyFileStore at ~/.cache/bainary/rag/

idx.add_artifact(artifact)               # index a binary
idx.add_artifact(other_artifact)         # corpus grows across binaries

# Natural-language search (lexical, not semantic — n-gram hashing trick)
hits = idx.search("parse HTTP request header", k=5)
for h in hits:
    print(h.score, h.binary_sha256, h.function.name)

# Find functions similar to a given one
neighbors = idx.search_similar(artifact.functions[0], k=5)

# Structured context block for LLM prompts (future D integration)
ctx = idx.retrieve_context(artifact.functions[0], k=5)  # {"neighbors": [(fn, score), ...]}

# Maintenance
removed = idx.remove_artifact(artifact.binary.sha256)
```

No embedding model is used. Vectorization is local (hashing trick over C-like tokens + 2-grams), deterministic, and runs in microseconds. Cosine similarity ranks hits.

### Subsystem E — Web GUI

```bash
pip install -e ".[gui]"
bainary-gui                          # → http://127.0.0.1:8787
```

Layout: function-tree sidebar, Monaco ASM + Code panels (Original /
Refinado / Diff), vis-network call graph with N-hop focus, and a
bottom panel for the SSE console, imports/exports/strings, and a RAG
search. `Settings` dialog persists to `.env` (key masked on read);
switching `LIFT_BACKEND` requires a server restart. All 5 subsystems
are exposed as JSON under `/api/*`; see
[Subsystem-E-GUI](docs/wiki/Subsystem-E-GUI.md) for the full endpoint
table.

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

286 tests total, all run in the fast lane (no slow marker needed for the GUI).

## Cache

**Lift cache**: artifacts are cached at `$BAINARY_CACHE_DIR` (defaults to `~/.cache/bainary/`) keyed by the binary's sha256. The layout is sharded (`<root>/<sha[0:2]>/<sha[2:4]>/<sha>.json`). Cache entries are invalidated automatically when the Ghidra version changes. LRU-evicted at 200 entries by default.

**Refinement cache**: refined pseudo-C is cached at `~/.cache/bainary/refine/` keyed by `sha256(pseudo_c + model + prompt_version)`. Avoids re-spending LLM tokens on the same function + model.

```bash
export BAINARY_CACHE_DIR=/tmp/bainary-cache  # override lift cache location
```

## Documentation

Full documentation is in `docs/wiki/`:

- [Home](docs/wiki/Home.md) — index of all pages
- [Architecture](docs/wiki/Architecture.md) — system design
- [Subsystem A](docs/wiki/Subsystem-A-Lift.md) — lift
- [Subsystem B](docs/wiki/Subsystem-B-Graph.md) — graph
- [Subsystem D](docs/wiki/Subsystem-D-Refine.md) — refine
- [Subsystem C](docs/wiki/Subsystem-C-RAG.md) — rag
- [Subsystem E](docs/wiki/Subsystem-E-GUI.md) — web GUI
- [CLI reference](docs/wiki/CLI-Reference.md)
- [Development guide](docs/wiki/Development-Guide.md)
- [Examples](docs/wiki/Examples.md)

## License

MIT
