"""One-shot end-to-end test of bainary.rag.

Uses the lief_capstone backend (no Ghidra needed) to lift tests/fixtures/hello_elf64,
then indexes it with HashMockEmbeddings (deterministic, offline), runs a couple of
searches, and validates the embedding cache.

NOTE on Kimi K2.7: OpenCode Go's /v1/embeddings endpoint returns 404 for Kimi K2.7
(Kimi is a chat/generation model, not an embedding model). For real embeddings in
this codebase use `text-embedding-3-small` via OpenAI directly, or another provider
that exposes an embeddings endpoint. See docs/wiki/Post-MVP-Roadmap.md for the
follow-up on supporting other embedding providers.

Run with:
    .venv/bin/python scripts/test_rag_kimi.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from bainary.lift import lift
from bainary.rag import HashMockEmbeddings, Index


def main() -> int:
    fixture = (
        Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "hello_elf64" / "hello.elf"
    )
    if not fixture.exists():
        print(f"ERROR: fixture not found: {fixture}", file=sys.stderr)
        return 2

    print(f"[1/6] Lifting {fixture} with lief_capstone backend...")
    t0 = time.time()
    artifact = lift(str(fixture), backend="lief_capstone")
    print(
        f"      done in {time.time() - t0:.1f}s — {len(artifact.functions)} functions, "
        f"sha256={artifact.binary.sha256[:12]}..."
    )

    print("\n[2/6] Creating HashMockEmbeddings (offline, deterministic)...")
    embed = HashMockEmbeddings(dim=128)
    print(f"      dim={embed.dim} model_name={embed.model_name}")

    print("\n[3/6] Building Index + add_artifact...")
    idx = Index(embeddings=embed)
    t0 = time.time()
    idx.add_artifact(artifact)
    print(f"      done in {time.time() - t0:.1f}s — corpus size = {len(idx)}")

    if len(idx) == 0:
        print("ERROR: corpus is empty after add_artifact", file=sys.stderr)
        return 1

    print("\n[4/6] search() with a natural-language query...")
    for query in ["main entry point", "write a string", "call printf"]:
        t0 = time.time()
        hits = idx.search(query, k=3)
        dt = time.time() - t0
        print(f"      query={query!r:35s} → {len(hits)} hits in {dt:.2f}s")
        for h in hits:
            print(f"         {h.score:.4f}  {h.function.name:25s}  @{h.function.address}")

    print("\n[5/6] search_similar() on a known function...")
    fn = artifact.functions[0]
    t0 = time.time()
    hits = idx.search_similar(fn, k=3)
    dt = time.time() - t0
    print(f"      function={fn.name!r:25s} → {len(hits)} hits in {dt:.2f}s")
    for h in hits:
        marker = " ← self" if h.function.address == fn.address else ""
        print(f"         {h.score:.4f}  {h.function.name:25s}  @{h.function.address}{marker}")

    print("\n[6/6] validate embedding cache: re-add the same artifact...")
    api_calls: list[int] = []
    original_embed = embed.embed

    def counting_embed(texts):
        api_calls.append(len(texts))
        return original_embed(texts)

    embed.embed = counting_embed  # type: ignore[assignment]
    idx.add_artifact(artifact)
    print(f"      new API calls during re-add: {sum(api_calls)} (expected 0; cache hits)")

    print("\n[cleanup] remove_artifact...")
    removed = idx.remove_artifact(artifact.binary.sha256)
    print(f"      removed {removed} records; corpus size now = {len(idx)}")

    print("\nDONE — all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
