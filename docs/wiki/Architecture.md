# Architecture

High-level design of the bAInary platform.

## Subsystems

```
┌─────────────────────────────────────────────────────────────────────┐
│                         bAInary Platform                             │
├─────────────┬───────────────┬───────────────┬───────────────┬────────┤
│  A: Lift    │  B: Graph     │  C: RAG       │  D: Refine    │ E:GUI  │
│              │               │               │               │(future)│
│ parse        │ NetworkX      │ embeddings    │ LLM clients   │        │
│ decompile    │ queries       │ vector store  │ cache         │        │
│ cache        │ serialization │ cross-binary  │ multi-provider│        │
├──────┬───────┴──────┬────────┴───────┬───────┴───────┬───────┴────────┤
│   ghidra_headless  │  lief_capstone  │ numpy, mock   │ openai,        │
│   (Ghidra JVM)     │  (LIEF+Capstone)│ (MVP)         │ anthropic,     │
│                    │                │ chromadb etc  │ mock           │
│                    │                │ (future)      │                │
└────────────────────┴────────────────┴───────────────┴────────────────┘
```

## Design principles

1. **Pluggable backends** — Every subsystem uses ABCs/strategies: `LifterBackend`, `LLMClient`, `EmbeddingClient`, `VectorStore`. Adding a new backend means one new file, no changes to consumers.

2. **Immutable contracts** — `BinaryArtifact` is the stable contract between A → B → C → D. It's Pydantic-validated and schema-versioned.

3. **Cache by default** — A (sha256 + Ghidra version), D (sha256 + model + prompt version), and C (sha256 + model + text_version for embeddings, sha256 + index for the vector store) cache results to avoid expensive recomputation.

4. **Partial failures** — If Ghidra fails to decompile one function, the LLM fails on one call, or the embedding API fails on one text, the rest of the artifact survives.

5. **Fast lane** — Tests that don't need Ghidra run in <1s. Tests that need Ghidra are marked `@pytest.mark.slow` and run separately.

## Data flow

```
Binary (.exe, .elf, .macho)
    │
    ▼
┌───────────────────┐
│  A: Lift           │  Ghidra / LIEF+Capstone
│  bainary.lift      │
└────────┬──────────┘
         │ BinaryArtifact (JSON + Python objects)
         ▼
┌───────────────────┐
│  B: Graph          │  NetworkX DiGraph
│  bainary.graph     │
└────────┬──────────┘
         │ BinaryArtifact + CallGraph
         ▼
┌───────────────────┐
│  C: RAG            │  EmbeddingClient + VectorStore
│  bainary.rag       │  (OpenAI / mock; numpy+json MVP)
└────────┬──────────┘
         │ SearchHits / retrieve_context
         ▼
┌───────────────────┐
│  D: Refine         │  LLM (OpenAI/Anthropic/Mock)
│  bainary.refine    │
└────────┬──────────┘
         │ BinaryArtifact (refined pseudo-C)
         ▼
    Output: refined decompilation
```

## Module layout

```
src/bainary/
├── __init__.py
├── lift/              # Subsystem A
│   ├── api.py         #    lift() public API
│   ├── artifact.py    #    dataclasses
│   ├── schema.py      #    Pydantic models
│   ├── cache.py       #    ArtifactCache
│   ├── cli.py         #    CLI (entry point: bainary-lift)
│   ├── __main__.py    #    python -m bainary.lift
│   ├── errors.py      #    exception hierarchy
│   └── backends/
│       ├── base.py          # LifterBackend ABC
│       ├── ghidra_headless.py
│       ├── lief_capstone.py
│       └── postscript.py    # Jython script for Ghidra
│
├── graph/             # Subsystem B
│   ├── callgraph.py   #    CallGraph class
│   ├── __init__.py    #    re-exports
│   └── errors.py      #    GraphError
│
├── rag/               # Subsystem C
│   ├── index.py       #    Index class (orchestrator)
│   ├── client.py      #    EmbeddingClient ABC + implementations
│   ├── store.py       #    VectorStore ABC + InMemoryStore / NumpyFileStore
│   ├── text.py        #    build_text() (pseudocode first, ASM fallback)
│   ├── __init__.py    #    re-exports
│   └── errors.py      #    RagError
│
└── refine/            # Subsystem D
    ├── refiner.py     #    Refiner class
    ├── client.py      #    LLMClient ABC + implementations
    ├── prompts.py     #    build_prompt()
    ├── cache.py       #    RefinementCache
    ├── __init__.py    #    re-exports
    └── errors.py      #    RefineError
```

## Exception hierarchy

```
BainaryError                      (lift/errors.py)
├── LifterError                    (backend failed)
├── SchemaValidationError          (JSON validation)
├── GraphError                     (graph/errors.py)
├── RagError                       (rag/errors.py)
└── RefineError                    (refine/errors.py)
```

## Dependencies

```
Runtime:
    lief>=0.14           Binary format parsing
    pydantic>=2.6        Schema validation
    typer>=0.12          CLI
    capstone>=5.0        Disassembly (lief_capstone backend)
    networkx>=3.2        Call graph (subsystem B)
    numpy>=1.26          Vector store + cosine sim (subsystem C)
    openai>=1.0          Embeddings + LLM client (subsystems C and D)
    anthropic>=0.20      Anthropic-compatible LLM client (subsystem D)

External:
    Ghidra 11.x + Java 21+  (ghidra_headless backend)

Dev:
    pytest>=8, pytest-mock
    ruff
    mypy
    pre-commit
```
