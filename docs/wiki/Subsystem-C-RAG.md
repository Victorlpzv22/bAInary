# Subsystem C — Cross-binary function search

Cross-binary textual-similarity index of functions. Given one or many `BinaryArtifact`s, vectorize each function's text (pseudocode first, ASM fallback) and search the corpus with natural-language queries or find functions similar to a given one.

**No embedding model is used.** Vectorization is local: the default `HashingTextVectorizer` applies the **hashing trick** over C-like tokens and 2-grams, producing a fixed-dim float vector per function. Cosine similarity ranks hits. This means: no API key, no network, no cost, deterministic results, runs in air-gapped environments.

```
  BinaryArtifact(s)  ──>  Index.add_artifact()  ──>  cross-binary corpus
                              │
                              ├── For each function:
                              │   1. build_text(fn)  (pseudocode || ASM)
                              │   2. record-id exists? skip (no-op re-add)
                              │   3. HashingTextVectorizer.vectorize([text])
                              │   4. upsert into VectorStore (numpy+JSON MVP)
                              │
  "parse HTTP request"  ──>  Index.search()       ──>  list[SearchHit]
  Function              ──>  Index.search_similar() ──> list[SearchHit]
  Function              ──>  Index.retrieve_context() → {"neighbors": [(fn, score), ...]}
```

## Concepts

- **`TextualVectorizer`** — ABC. `vectorize(texts) -> list[list[float]]`. Implementations:
  - `HashingTextVectorizer` (default) — deterministic, offline, no state, no model. Tokens are C-like identifiers + numbers + operators; n-grams of size 1 and 2 are hashed into a fixed-dim vector, weighted with sub-linear TF and L2-normalized. Same text always yields the same vector; similar texts (sharing many n-grams) yield similar vectors.
  - *Future:* TF-IDF, character n-grams, n-gram with stemming, or any other text→vector transform — drop-in subclass of `TextualVectorizer`.
- **`VectorStore`** — ABC. Stores `VectorRecord(id, vector, function_dict, binary_sha256, name, address, source, text_hash)`. Implementations:
  - `InMemoryStore` — dict-backed; used in tests.
  - `NumpyFileStore` — persistent numpy + JSON at `~/.cache/bainary/rag/`. Recovers gracefully from corrupt files.
  - *Future:* ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib — drop-in subclasses of `VectorStore`.
- **`Index`** — orchestrator. Owns a `TextualVectorizer` and a `VectorStore`. Provides `add_artifact`, `search`, `search_similar`, `retrieve_context`, `remove_artifact`.
- **`SearchHit`** — `(function, binary_sha256, score, source)`. Score is cosine similarity in [-1, 1].

## Public API

```python
from bainary.rag import Index, create_textual_vectorizer

vec = create_textual_vectorizer()        # default: HashingTextVectorizer(dim=1024)
idx = Index(vectorizer=vec)              # defaults to NumpyFileStore at ~/.cache/bainary/rag/

# Build a cross-binary corpus
idx.add_artifact(artifact)
idx.add_artifact(other_artifact)

# Natural-language search (lexical, not semantic)
hits = idx.search("parse HTTP request header", k=5)
for h in hits:
    print(h.score, h.binary_sha256, h.function.name, h.source)

# Similarity to a known function (itself is the top hit if indexed)
neighbors = idx.search_similar(artifact.functions[0], k=5)

# Structured context for LLM prompts (future integration with D)
ctx = idx.retrieve_context(artifact.functions[0], k=5)
# {"neighbors": [(function, score), ...]}

# Maintenance
removed = idx.remove_artifact(artifact.binary.sha256)
print(f"{len(idx)} functions in the corpus")
```

## Cache and persistence

- **Vector store** at `~/.cache/bainary/rag/store.npy` + `~/.cache/bainary/rag/records.json` when using `NumpyFileStore`.
- **No embedding cache** — vectorization is local and microsecond-scale, so caching would be premature optimization.

Both files tolerate corruption: a malformed file is logged and the store starts empty rather than raising.

## Identity and re-adding

Records are keyed by `id = sha256(binary_sha256 + ":" + fn.address)`. Re-adding the same artifact is a **no-op** (the `id` is already present in the store, so `add_artifact` skips it).

If a function's address changes between lifts (e.g. a different Ghidra version), the old `VectorRecord` becomes an orphan. See "Known issues" below.

## Text construction (`build_text`)

```text
Function: `main`  (sig: int main(int argc, char ** argv))
< pseudocode if available
  else: // no decompilation available
        followed by assembly listing >
```

- **Pseudocode first** (richest signal).
- **ASM fallback** (lief_capstone artifacts have no decompilation but can still be indexed).
- **Empty text** → function is skipped by default (`skip_no_text=True`); pass `skip_no_text=False` to make it raise `RagError` instead.

`TEXT_VERSION = "v1"` is reserved for future text-format changes; the current vectorizer ignores it.

## Backends

| Component | Current | Future |
|---|---|---|
| Vectorizer | HashingTextVectorizer (n-gram hashing) | TF-IDF, character n-grams, n-gram with stemming |
| Vector store | InMemory, NumpyFileStore (numpy+JSON) | ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib |

Adding a new backend means one new class implementing the `TextualVectorizer` or `VectorStore` ABC and (for vectorizer) one line in `create_textual_vectorizer`. Consumers (`Index`) don't change.

## Testing

All tests use `HashingTextVectorizer` + `InMemoryStore` — no network, no API key, no cost, deterministic. Persistence tests use `NumpyFileStore(root=tmp_path)` to keep the user's `~/.cache/bainary/rag/` untouched.

```bash
pytest tests/test_rag.py -v
```

40 tests, all fast lane (no `@pytest.mark.slow`). Covers:

- Text construction (name/signature/pseudo/ASM fallback).
- HashingTextVectorizer determinism, dim handling, similar-text higher score, empty-text handling.
- InMemoryStore upsert/get/search/remove.
- NumpyFileStore persistence + corrupt recovery.
- Index corpus lifecycle (add, re-add no-op, remove).
- Cross-binary search: a `parse_http_header` finds `parse_https_header` as the closest non-self hit.
- Partial-failure handling (one function's vectorize failure doesn't abort).
- `retrieve_context` shape for future D integration.

## Out of scope (for C MVP)

The full post-MVP backlog lives in **[Post-MVP Roadmap](Post-MVP-Roadmap)**. Highlights for C:

- **C↔D integration** — inject retrieved context into the refine prompt.
- **Additional `TextualVectorizer` implementations** (TF-IDF, character n-grams, stemming).
- **Additional `VectorStore` backends** (ChromaDB, LanceDB, sqlite-vec, FAISS, hnswlib).
- **Search features** — metadata filtering, hybrid lexical+lexical, per-binary sub-corpus queries, MMR diversity.
- **Corpus management** — `gc_orphans`, corpus diffing, export/import.
- **Operational** — CLI, statistics.
- **Performance** — batch / parallel vectorization, ANN indexes.

When any of these lands, update both the roadmap (move from `- [ ]` to `- [x]`) and this page if the section changes.

## Known issues

- **Address shifting on re-lift**: if re-lifting with a different Ghidra version shifts a function's address, the old `VectorRecord` becomes an orphan (its `id` no longer matches). Future: `gc_orphans(binary_sha256, current_artifact)` to sweep stale ids. Post-MVP.
- **No semantic similarity**: the hashing trick is lexical. Two functions that do the same thing with very different tokens (e.g. `if (x>0)` vs `if (positive(x))`) will not rank close. A real semantic model would help here, but introducing it would contradict the "no embedding model" decision. Post-MVP if requirements change.
