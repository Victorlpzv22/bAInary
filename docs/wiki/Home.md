# bAInary Wiki

AI-assisted reverse engineering of compiled binaries. Lift PE/ELF/Mach-O binaries, build call graphs, and refine decompiled pseudo-C with an LLM.

## Subsystems

| Subsystem | Status | Description |
|---|---|---|
| [**A — Lift**](Subsystem-A-Lift) | ✅ Complete | Binary parsing & lifting: extract functions, ASM, pseudo-C, CFG, imports/exports |
| [**B — Graph**](Subsystem-B-Graph) | ✅ Complete | Build a `networkx.DiGraph` from a lifted binary: queries, cycles, shortest paths |
| [**C — Cross-binary search**](Subsystem-C-RAG) | ✅ Complete | Cross-binary function index; lexical similarity (hashing trick) for search and retrieve context |
| [**D — Refine**](Subsystem-D-Refine) | ✅ Complete | LLM-based pseudo-C refinement: rename variables, remove warnings, add comments |
| [**E — GUI**](Subsystem-E-GUI) | ✅ Complete | Web GUI: Monaco editor + vis-network + SSE; lift/refine/RAG from the browser |

## Quick links

- [Architecture overview](Architecture)
- [CLI reference](CLI-Reference)
- [Usage examples](Examples)
- [Development guide](Development-Guide)
- [Post-MVP roadmap](Post-MVP-Roadmap)
- [README](/README.md)

## Stats

- **286 tests** (all fast — no slow marker needed for the GUI)
- **46 source files** across 5 subsystems
- **3 lifting backends** (Ghidra, Lief+Capstone, pluggable)
- **3 LLM providers** (OpenAI-compatible, Anthropic-compatible, Mock)
- **2 textual vectorizers** (HashingTextVectorizer default, TfidfTextVectorizer; no model, offline)
- **2 vector store backends** (InMemory, NumpyFileStore; ChromaDB/LanceDB/sqlite-vec/FAISS future)
- **3 CLI entry points** (bainary-lift, bainary-rag, **bainary-gui**)
- **1 web GUI** (FastAPI + Monaco + vis-network + SSE, single-tenant loopback)
- **4 binary formats** (PE, ELF, Mach-O)
- **4 architectures** (x86, x64, ARM, ARM64)
