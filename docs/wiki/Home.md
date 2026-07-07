# bAInary Wiki

AI-assisted reverse engineering of compiled binaries. Lift PE/ELF/Mach-O binaries, build call graphs, and refine decompiled pseudo-C with an LLM.

## Subsystems

| Subsystem | Status | Description |
|---|---|---|
| [**A — Lift**](Subsystem-A-Lift) | ✅ Complete | Binary parsing & lifting: extract functions, ASM, pseudo-C, CFG, imports/exports |
| [**B — Graph**](Subsystem-B-Graph) | ✅ Complete | Build a `networkx.DiGraph` from a lifted binary: queries, cycles, shortest paths |
| [**C — RAG/Embeddings**](Subsystem-C-RAG) | ✅ Complete | Cross-binary semantic index of functions; search and retrieve context for LLM prompts |
| [**D — Refine**](Subsystem-D-Refine) | ✅ Complete | LLM-based pseudo-C refinement: rename variables, remove warnings, add comments |
| E — GUI | ❌ Not started | Visual interface |

## Quick links

- [Architecture overview](Architecture)
- [CLI reference](CLI-Reference)
- [Usage examples](Examples)
- [Development guide](Development-Guide)
- [Post-MVP roadmap](Post-MVP-Roadmap)
- [README](/README.md)

## Stats

- **151 tests** (144 fast, 7 slow with Ghidra)
- **29 source files** across 4 subsystems
- **3 lifting backends** (Ghidra, Lief+Capstone, pluggable)
- **3 LLM providers** (OpenAI-compatible, Anthropic-compatible, Mock)
- **2 embedding providers** (OpenAI-compatible, deterministic Mock)
- **2 vector store backends** (InMemory, NumpyFileStore; ChromaDB/LanceDB/sqlite-vec/FAISS future)
- **4 binary formats** (PE, ELF, Mach-O)
- **4 architectures** (x86, x64, ARM, ARM64)
