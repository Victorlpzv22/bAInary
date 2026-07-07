"""One-shot end-to-end test of bainary.rag.

Uses the lief_capstone backend (no Ghidra needed) to lift tests/fixtures/hello_elf64,
then indexes it with HashingTextVectorizer (deterministic, offline, no embeddings),
runs a couple of searches, and validates corpus lifecycle.

Run with:
    .venv/bin/python scripts/test_rag_kimi.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from bainary.lift import lift
from bainary.rag import HashingTextVectorizer, Index


def main() -> int:
    fixture = (
        Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "hello_elf64" / "hello.elf"
    )
    if not fixture.exists():
        print(f"ERROR: fixture not found: {fixture}", file=sys.stderr)
        return 2

    print(f"[1/5] Lifting {fixture} with lief_capstone backend...")
    t0 = time.time()
    artifact = lift(str(fixture), backend="lief_capstone")
    print(
        f"      done in {time.time() - t0:.1f}s — {len(artifact.functions)} functions, "
        f"sha256={artifact.binary.sha256[:12]}..."
    )

    print("\n[2/5] Creating HashingTextVectorizer (offline, deterministic)...")
    vec = HashingTextVectorizer(dim=128)
    print(f"      dim={vec.dim}")

    print("\n[3/5] Building Index + add_artifact...")
    idx = Index(vectorizer=vec)
    t0 = time.time()
    idx.add_artifact(artifact)
    print(f"      done in {time.time() - t0:.3f}s — corpus size = {len(idx)}")

    if len(idx) == 0:
        print("ERROR: corpus is empty after add_artifact", file=sys.stderr)
        return 1

    print("\n[4/5] search() + search_similar()...")
    for query in ["main entry point", "write a string", "call printf"]:
        hits = idx.search(query, k=3)
        print(f"      query={query!r:35s} → {len(hits)} hits")
        for h in hits:
            print(f"         {h.score:.4f}  {h.function.name:25s}  @{h.function.address}")

    fn = artifact.functions[0]
    hits = idx.search_similar(fn, k=3)
    print(f"      similar-to={fn.name!r:25s} → {len(hits)} hits")
    for h in hits:
        marker = " ← self" if h.function.address == fn.address else ""
        print(f"         {h.score:.4f}  {h.function.name:25s}  @{h.function.address}{marker}")

    print("\n[5/5] re_add_is_noop + remove_artifact...")
    idx.add_artifact(artifact)  # should be a no-op
    assert len(idx) == 9
    removed = idx.remove_artifact(artifact.binary.sha256)
    print(f"      removed {removed} records; corpus size now = {len(idx)}")

    print("\nDONE — all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
