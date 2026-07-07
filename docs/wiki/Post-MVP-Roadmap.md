# Post-MVP Roadmap

A consolidated list of work that has been **deliberately deferred** beyond the MVP of each subsystem. Each entry links back to the subsystem spec/wiki for context. New entries can be added as subsystems mature.

## Subsystem C — RAG / Embeddings

The MVP (semantic function index, natural-language search, cross-binary corpus) is complete. Below is the post-MVP backlog.

### Cross-subsystem integration

- [ ] **C↔D prompt injection** — when `Refiner.refine` processes a function, query `Index.retrieve_context(fn, k=5)` and inject the neighbors as "similar functions in the corpus" context into the LLM prompt. Currently the integration API exists (`retrieve_context`) but is not wired into `Refiner`.
- [ ] **C↔E (GUI)** — render the corpus as a graph or table; clicking a function shows its neighbors with scores and source binaries.

### Embedding providers

- [ ] **Cohere, Voyage AI, local sentence-transformers** — additional `EmbeddingClient` subclasses.
- [ ] **Batch / parallel embedding API calls** — current is sequential; many APIs support true batching for cost and latency.
- [ ] **Embedding model rotation** — switch model in-place without forcing a full re-index; use a per-model `VectorStore` namespace or keyed collections.
- [ ] **Investigate embedding availability on OpenCode Go** — Kimi K2.7 (and likely other chat models on `/v1/embeddings`) returns 404 from `https://opencode.ai/zen/go/v1/embeddings`. Confirmed 2026-07-07 with the end-to-end test in `scripts/test_rag_kimi.py`. Two paths: (a) document that OpenCode Go is chat-only and steer users to `text-embedding-3-small` direct via OpenAI, (b) investigate if OpenCode Go has a separate embeddings route.

### Vector store backends

The `VectorStore` ABC is designed for drop-in subclasses. Each of these becomes a new file (no consumer changes).

- [ ] **ChromaDB backend** — persistent client, native metadata filtering.
- [ ] **LanceDB backend** — columnar, good for larger corpora.
- [ ] **sqlite-vec backend** — single `.db` file, lightweight.
- [ ] **FAISS / hnswlib backend** — faster approximate nearest neighbor at scale.

### Search features

- [ ] **Metadata filtering** — "only libc", "only binary X", name LIKE, address range.
- [ ] **Hybrid lexical + vector search** — BM25 over function names/signatures plus cosine over vectors; combine scores.
- [ ] **Per-binary sub-corpus queries** — `idx.search_in(binary_sha, query, k=...)` to scope a search to one binary.
- [ ] **Result diversity (MMR)** — replace pure top-k with Maximal Marginal Relevance so neighbors aren't near-duplicates.

### Corpus management

- [ ] **`gc_orphans(binary_sha256, current_artifact)`** — sweep stale `VectorRecord`s when re-lifting with a different Ghidra version shifts function addresses. Currently the orphan would just linger.
- [ ] **Corpus diffing** — "what's new in this build vs the previous build of the same binary?".
- [ ] **Export / import corpus** to a portable format (parquet + json metadata) for sharing across teams/machines.

### Operational

- [ ] **CLI** — `bainary-rag index path/to/bin/`, `bainary-rag search "..."`, `bainary-rag stats`. Library-only today.
- [ ] **Token / cost tracking** per embedding call.
- [ ] **Vector store statistics** — corpus size, dim distribution, density, age of entries.

### Known issues (carried over)

- **Address shifting on re-lift** — see `gc_orphans` above.
- **Embedding dim mismatch** — currently a hard `RagError`; could offer automatic store re-create for the (rare) case of switching models in place.

---

## How to use this page

When starting work on any post-MVP item:

1. Move the checkbox from `- [ ]` to `- [x]` (or remove the entry once done).
2. If the work needs a design pass (most do — they touch the public API), use the **brainstorming** skill first to validate scope and approach.
3. If it's a small isolated change (e.g. a new `EmbeddingClient` subclass), you can skip brainstorming and go straight to TDD via the **test-driven-development** skill.
4. Update the corresponding subsystem wiki/spec page when the item lands.
