# Architecture

High-level design of the bAInary platform.

## Subsystems

```
┌─────────────────────────────────────────────────────────────────────┐
│                         bAInary Platform                             │
├─────────────┬───────────────┬───────────────┬───────────────┬────────┤
│  A: Lift    │  B: Graph     │  C: Search    │  D: Refine    │ E:GUI  │
│              │               │               │               │(future)│
│ parse        │ NetworkX      │ textual       │ LLM clients   │        │
│ decompile    │ queries       │ vectorizer    │ cache         │        │
│ cache        │ serialization │ vector store  │ multi-provider│        │
│              │               │ cross-binary  │               │        │
├──────┬───────┴──────┬────────┴───────┬───────┴───────┬───────┴────────┤
│   ghidra_headless  │  lief_capstone  │ numpy, mock   │ openai,        │
│   (Ghidra JVM)     │  (LIEF+Capstone)│ (MVP)         │ anthropic,     │
│                    │                │ chromadb etc  │ mock           │
│                    │                │ (future)      │                │
└────────────────────┴────────────────┴───────────────┴────────────────┘
```

## Design principles

1. **Pluggable backends** — Every subsystem uses ABCs/strategies: `LifterBackend`, `LLMClient`, `TextualVectorizer`, `VectorStore`. Adding a new backend means one new file, no changes to consumers.

2. **Immutable contracts** — `BinaryArtifact` is the stable contract between A → B → C → D. It's Pydantic-validated and schema-versioned.

3. **Cache by default** — A (sha256 + Ghidra version) and D (sha256 + model + prompt version) cache results to avoid expensive recomputation. C does not need a cache — vectorization is local and microsecond-scale.

4. **Partial failures** — If Ghidra fails to decompile one function, the LLM fails on one call, or the vectorizer fails on one function, the rest of the artifact survives.

5. **No embedding model, no network, no API key in C** — vectorization is local (hashing trick by default). The subsystem can be used in air-gapped environments.

6. **Fast lane** — Tests that don't need Ghidra run in <1s. Tests that need Ghidra are marked `@pytest.mark.slow` and run separately.

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
│  C: Search         │  TextualVectorizer + VectorStore
│  bainary.rag       │  (hashing trick + numpy+json MVP)
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
│   ├── index.py       #    Index class (orchestrator) + gc_orphans, search filters
│   ├── vectorize.py   #    TextualVectorizer ABC + HashingTextVectorizer + TfidfTextVectorizer
│   ├── store.py       #    VectorStore ABC + InMemoryStore / NumpyFileStore
│   ├── text.py        #    build_text() (pseudocode first, ASM fallback)
│   ├── cli.py         #    bainary-rag entry point (index / search / stats)
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
    openai>=1.0          LLM client (subsystem D)
    anthropic>=0.20      Anthropic-compatible LLM client (subsystem D)

External:
    Ghidra 11.x + Java 21+  (ghidra_headless backend)

Dev:
    pytest>=8, pytest-mock
    ruff
    mypy
    pre-commit
```
