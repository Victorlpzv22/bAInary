# Post-MVP Roadmap

A consolidated list of work that has been **deliberately deferred** beyond the MVP of each subsystem. Each entry links back to the subsystem spec/wiki for context. New entries can be added as subsystems mature.

## Subsystem C — Cross-binary function search

The MVP (cross-binary function index, lexical similarity, search, retrieve_context) is complete. **No embedding model is used — the user has decided never to use one** (decision 2026-07-07). Below is the post-MVP backlog.

### Cross-subsystem integration

- [ ] **C↔D prompt injection** — when `Refiner.refine` processes a function, query `Index.retrieve_context(fn, k=5)` and inject the neighbors as "similar functions in the corpus" context into the LLM prompt. The integration API exists (`retrieve_context`) but is not wired into `Refiner`.
- [ ] **C↔E (GUI)** — render the corpus as a graph or table; clicking a function shows its neighbors with scores and source binaries.

### Textual vectorizers (no embeddings)

The `TextualVectorizer` ABC is designed for drop-in subclasses. New implementations may improve ranking quality without changing consumers.

- [ ] **TF-IDF vectorizer** — learned vocabulary, sparse vectors, better exact-match recall.
- [ ] **Character n-grams** — robust to identifier renaming (`if (x>0)` vs `if (positive(x))`).
- [ ] **n-gram with stemming** — collapse `running` / `runs` / `ran` to a common token.
- [ ] **Sub-word tokenization** (BPE) — better OOV handling for unusual identifiers.
- [ ] **Batch / parallel vectorization** — current is sequential; for large artifacts.
- [ ] **Vectorizer rotation** — switch implementation in place; the `VectorStore` stores raw vectors so rotation requires a full re-index by design.

### Vector store backends

The `VectorStore` ABC is designed for drop-in subclasses. Each of these becomes a new file (no consumer changes).

- [ ] **ChromaDB backend** — persistent client, native metadata filtering.
- [ ] **LanceDB backend** — columnar, good for larger corpora.
- [ ] **sqlite-vec backend** — single `.db` file, lightweight.
- [ ] **FAISS / hnswlib backend** — faster approximate nearest neighbor at scale.

### Search features

- [ ] **Metadata filtering** — "only libc", "only binary X", name LIKE, address range.
- [ ] **Hybrid lexical + lexical** — combine the `TextualVectorizer` cosine score with a BM25 over function names/signatures.
- [ ] **Per-binary sub-corpus queries** — `idx.search_in(binary_sha, query, k=...)` to scope a search to one binary.
- [ ] **Result diversity (MMR)** — replace pure top-k with Maximal Marginal Relevance so neighbors aren't near-duplicates.

### Corpus management

- [ ] **`gc_orphans(binary_sha256, current_artifact)`** — sweep stale `VectorRecord`s when re-lifting with a different Ghidra version shifts function addresses. Currently the orphan would just linger.
- [ ] **Corpus diffing** — "what's new in this build vs the previous build of the same binary?".
- [ ] **Export / import corpus** to a portable format (parquet + json metadata) for sharing across teams/machines.

### Operational

- [ ] **CLI** — `bainary-rag index path/to/bin/`, `bainary-rag search "..."`, `bainary-rag stats`. Library-only today.
- [ ] **Vector store statistics** — corpus size, dim distribution, density, age of entries.

### Known issues (carried over)

- **Address shifting on re-lift** — see `gc_orphans` above.
- **Lexical, not semantic** — the hashing trick doesn't recognize synonyms or paraphrases. Acceptable given the "no embedding model" decision; documented in `Subsystem-C-RAG.md`.

---

## How to use this page

When starting work on any post-MVP item:

1. Move the checkbox from `- [ ]` to `- [x]` (or remove the entry once done).
2. If the work needs a design pass (most do — they touch the public API), use the **brainstorming** skill first to validate scope and approach.
3. If it's a small isolated change (e.g. a new `TextualVectorizer` subclass), you can skip brainstorming and go straight to TDD via the **test-driven-development** skill.
4. Update the corresponding subsystem wiki/spec page when the item lands.
