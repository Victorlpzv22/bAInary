# Subsystem C — RAG / Embeddings

Cross-binary semantic index of functions. Given one or many `BinaryArtifact`s, embed each function's text (pseudocode first, ASM fallback) and store the vector + metadata. Search the corpus with natural-language queries or find functions similar to a given one.

```
  BinaryArtifact(s)  ──>  Index.add_artifact()  ──>  cross-binary corpus
                              │
                              ├── For each function:
                              │   1. build_text(fn)  (pseudocode || ASM)
                              │   2. text_hash check → skip if unchanged
                              │   3. Embedding cache lookup (sha256(text+model+TEXT_VERSION))
                              │   4. embed via EmbeddingClient (OpenAI / Mock)
                              │   5. upsert into VectorStore (numpy+JSON MVP)
                              │
  "parse HTTP request"  ──>  Index.search()       ──>  list[SearchHit]
  Function              ──>  Index.search_similar() ──> list[SearchHit]
  Function              ──>  Index.retrieve_context() → {"neighbors": [(fn, score), ...]}
```

## Concepts

- **`EmbeddingClient`** — ABC. `embed(texts) -> list[list[float]]`. Implementations:
  - `OpenAICompatibleEmbeddings` — uses the `openai` SDK; works with OpenAI, OpenCode Go, Ollama, any OpenAI-compatible API.
  - `HashMockEmbeddings` — deterministic SHA-256-bucketed vectors, no network, no API key. Used in tests and local exploration.
- **`VectorStore`** — ABC. Stores `VectorRecord(id, vector, function_dict, binary_sha256, name, address, source, text_hash)`. Implementations:
  - `InMemoryStore` — dict-backed; used in tests.
  - `NumpyFileStore` — persistent numpy + JSON at `~/.cache/bainary/rag/`. Recovers gracefully from corrupt files.
  - *Future:* ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib — drop-in subclasses of `VectorStore`.
- **`Index`** — orchestrator. Owns an `EmbeddingClient`, a `VectorStore`, and a file-based `EmbeddingCache`. Provides `add_artifact`, `search`, `search_similar`, `retrieve_context`, `remove_artifact`.
- **`SearchHit`** — `(function, binary_sha256, score, source)`. Score is cosine similarity in [-1, 1].

## Public API

```python
import os
from bainary.rag import Index, create_embedding_client

# OpenCode Go → text-embedding-3-small
embed = create_embedding_client(
    provider="openai",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="text-embedding-3-small",
)

# Or, for tests / offline:
embed = create_embedding_client(provider="mock", dim=64)

idx = Index(embeddings=embed)         # defaults to NumpyFileStore at ~/.cache/bainary/rag/

# Build a cross-binary corpus
idx.add_artifact(artifact)
idx.add_artifact(other_artifact)

# Natural-language search
hits = idx.search("parse HTTP request header", k=5)
for h in hits:
    print(h.score, h.binary_sha256, h.function.name, h.source)

# Similarity to a known function
neighbors = idx.search_similar(artifact.functions[0], k=5)

# Structured context for LLM prompts (future integration with D)
ctx = idx.retrieve_context(artifact.functions[0], k=5)
# {"neighbors": [(function, score), ...]}

# Maintenance
removed = idx.remove_artifact(artifact.binary.sha256)
print(f"{len(idx)} functions in the corpus")
```

## Cache layout

- **Embedding cache** (per vector) at `~/.cache/bainary/rag/embeddings/<sha[0:2]>/<sha[2:4]>/<sha>.json`. Key: `sha256(text + model + TEXT_VERSION)`. Same pattern as `bainary.lift.cache.ArtifactCache` and `bainary.refine.cache.RefinementCache`.
- **Vector store** (the corpus itself) at `~/.cache/bainary/rag/store.npy` + `~/.cache/bainary/rag/records.json` when using `NumpyFileStore`.

Both files tolerate corruption: a malformed file is logged and the store starts empty rather than raising.

## Identity and re-embedding

Records are keyed by `id = sha256(binary_sha256 + ":" + fn.address)`. Re-adding the same artifact is a **no-op** if the function's `text_hash` matches. If the pseudo-C changed (e.g. after subsystem D refined it), the new text triggers re-embedding and the record is overwritten.

This is the same pattern as D's refinement cache: spend tokens once per (function, model), never twice for identical inputs.

## Text construction (`build_text`)

```text
Function: `main`  (sig: int main(int argc, char ** argv))
< pseudocode if available
  else: // no decompilation available
        followed by assembly listing >
```

- **Pseudocode first** (richest semantic signal).
- **ASM fallback** (lief_capstone artifacts have no decompilation but can still be indexed).
- **Empty text** → function is skipped by default (`skip_no_text=True`); pass `skip_no_text=False` to make it raise `RagError` instead.

`TEXT_VERSION = "v1"` is part of the embedding cache key, so changing the text format invalidates all cached vectors.

## Backends

| Component | Current | Future |
|---|---|---|
| Embeddings | OpenAI-compatible, HashMock | Cohere, Voyage, local sentence-transformers |
| Vector store | InMemory, NumpyFileStore (numpy+JSON) | ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib |

Adding a new backend means one new class implementing the `EmbeddingClient` or `VectorStore` ABC and one line in `create_embedding_client` (for embeddings). Consumers (`Index`) don't change.

## Testing

All tests use `HashMockEmbeddings` + `InMemoryStore` — no network, no API key, no cost, deterministic. Persistence tests use `NumpyFileStore(root=tmp_path)` to keep the user's `~/.cache/bainary/rag/` untouched.

```bash
pytest tests/test_rag.py -v
```

41 tests, all fast lane (no `@pytest.mark.slow`). Covers:

- Text construction (name/signature/pseudo/ASM fallback).
- HashMock determinism and dim handling.
- `create_embedding_client` factory.
- InMemoryStore upsert/get/search/remove.
- NumpyFileStore persistence + corrupt recovery.
- Index corpus lifecycle (add, re-add no-op, remove).
- Embedding cache hit prevents duplicate API calls.
- Partial-failure handling (one function's embed failure doesn't abort).
- `retrieve_context` shape for future D integration.

## Out of scope (for C MVP)

The full post-MVP backlog lives in **[Post-MVP Roadmap](Post-MVP-Roadmap)** (consolidated for the whole project). Highlights for C:

- **C↔D integration** — inject retrieved context into the refine prompt. The `retrieve_context()` API is the integration point.
- **Additional `EmbeddingClient` providers** (Cohere, Voyage, local sentence-transformers).
- **Additional `VectorStore` backends** (ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib).
- **Search features** — metadata filtering ("only libc", "only binary X"), hybrid lexical + vector, per-binary sub-corpus queries, MMR diversity.
- **Corpus management** — `gc_orphans` for address shifting, corpus diffing, export/import.
- **Operational** — CLI (`bainary-rag`), token/cost tracking, statistics.
- **Performance** — batch / parallel embedding API calls, ANN indexes.

When any of these lands, update both the roadmap (move from `- [ ]` to `- [x]`) and this page if the section changes.

## Known issues

- **Address shifting on re-lift**: if re-lifting with a different Ghidra version shifts a function's address, the old `VectorRecord` becomes an orphan (its `id` no longer matches). Future: `gc_orphans(binary_sha256, current_artifact)` to sweep stale ids. Post-MVP.
