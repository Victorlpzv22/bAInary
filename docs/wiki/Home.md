# bAInary Wiki

AI-assisted reverse engineering of compiled binaries. Lift PE/ELF/Mach-O binaries, build call graphs, and refine decompiled pseudo-C with an LLM.

## Subsystems

| Subsystem | Status | Description |
|---|---|---|
| [**A — Lift**](Subsystem-A-Lift) | ✅ Complete | Binary parsing & lifting: extract functions, ASM, pseudo-C, CFG, imports/exports |
| [**B — Graph**](Subsystem-B-Graph) | ✅ Complete | Build a `networkx.DiGraph` from a lifted binary: queries, cycles, shortest paths |
| [**D — Refine**](Subsystem-D-Refine) | ✅ Complete | LLM-based pseudo-C refinement: rename variables, remove warnings, add comments |
| C — RAG/Embeddings | ❌ Not started | Semantic search across function corpora |
| E — GUI | ❌ Not started | Visual interface |

## Quick links

- [Architecture overview](Architecture)
- [CLI reference](CLI-Reference)
- [Usage examples](Examples)
- [Development guide](Development-Guide)
- [README](/README.md)

## Stats

- **110 tests** (103 fast, 7 slow with Ghidra)
- **23 source files** across 3 subsystems
- **3 lifting backends** (Ghidra, Lief+Capstone, pluggable)
- **3 LLM providers** (OpenAI-compatible, Anthropic-compatible, Mock)
- **4 binary formats** (PE, ELF, Mach-O)
- **4 architectures** (x86, x64, ARM, ARM64)
