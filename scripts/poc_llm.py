"""PoC: take a BinaryArtifact, build a CallGraph, send 2-3 functions to an LLM.

This is a proof-of-concept for subsystem D (LLM refinement). It validates
the end-to-end setup: lift a binary (A), build a call graph (B), and
refine the pseudo-C with a language model via the OpenCode Go API.

Requirements:
    pip install openai
    export OPENCODE_APIKEY="sk-..."  # your OpenCode Go key

Usage:
    python scripts/poc_llm.py <binary>
    python scripts/poc_llm.py tests/fixtures/loops_elf64/loops.elf
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running from repo root: add src/ to path so `bainary.*` resolves.
# Must come before any bainary.* imports.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openai import OpenAI  # noqa: E402

from bainary.graph import CallGraph  # type: ignore[import-untyped]  # noqa: E402
from bainary.lift import lift  # type: ignore[import-untyped]  # noqa: E402

# OpenCode Go API: OpenAI-compatible Chat Completions endpoint.
# Docs: https://opencode.ai/docs/es/go
OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "kimi-k2.7-code"  # code-specialized, good price/quality

# How many functions to send to the LLM. The PoC only refines a few
# (the smallest ones) to keep the request small and the output readable.
DEFAULT_NUM_FUNCTIONS = 3


def pick_smallest_functions(
    cg: CallGraph, n: int
) -> list[tuple[str, str]]:
    """Pick the N smallest functions (by pseudocode length) with valid pseudo-C.

    Returns a list of (name, pseudo_c) tuples.
    """
    candidates: list[tuple[str, str]] = []
    for node in cg.functions.values():
        if node.pseudocode and len(node.pseudocode.strip()) > 0:
            candidates.append((node.name, node.pseudocode))
    # Sort by pseudocode length (ascending) — smaller first
    candidates.sort(key=lambda x: len(x[1]))
    return candidates[:n]


def build_prompt(function_name: str, pseudo_c: str, caller_names: set[str]) -> str:
    """Build the refinement prompt for one function.

    The LLM's job: clean up the pseudo-C (rename variables, add types,
    fix warnings) while preserving the exact same behavior.
    """
    caller_list = ", ".join(sorted(caller_names)) or "(none — external entry point)"
    return f"""You are a senior reverse engineer. Refine the following decompiled C function from a binary.

Function: `{function_name}`
Callers: {caller_list}

Original decompiled C (from Ghidra, with anonymous variables and warnings):

```c
{pseudo_c}
```

Refine it:
1. Rename anonymous variables (iVar1, iVar2, auStack_8, in_RDI, etc.) to meaningful names based on their usage.
2. Remove Ghidra's `/* WARNING: ... */` comments unless they reveal something critical.
3. Fix the signature: parameter types, return type, and name.
4. Add a one-line comment explaining what the function does.
5. Keep the exact same behavior — this is decompilation, not rewriting.

Output ONLY the refined C code in a single code block. No prose before or after."""


def refine_function(
    client: OpenAI, model: str, function_name: str, pseudo_c: str, caller_names: set[str]
) -> str:
    """Send one function to the LLM and return the refined code."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        temperature=0.0,  # deterministic for RE
        messages=[
            {
                "role": "user",
                "content": build_prompt(function_name, pseudo_c, caller_names),
            }
        ],
    )
    content = response.choices[0].message.content or ""
    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```c"):
        content = content[3:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", type=Path, help="Path to a PE or ELF binary")
    parser.add_argument(
        "--backend", default="lief_capstone",
        help="Lifting backend (default: lief_capstone, fast; use ghidra_headless for real pseudo-C)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"OpenCode Go model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "-n", "--num-functions", type=int, default=DEFAULT_NUM_FUNCTIONS,
        help=f"Number of functions to refine (default: {DEFAULT_NUM_FUNCTIONS})",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENCODE_APIKEY")
    if not api_key:
        print("ERROR: OPENCODE_APIKEY not set. Export your OpenCode Go key first:", file=sys.stderr)
        print("  export OPENCODE_APIKEY='sk-...'", file=sys.stderr)
        return 2

    if not args.binary.exists():
        print(f"ERROR: {args.binary} not found", file=sys.stderr)
        return 1

    # 1. Lift (A)
    print(f"[1/3] Lifting {args.binary} with backend={args.backend}...")
    artifact = lift(args.binary, backend=args.backend, use_cache=False)

    # 2. Build call graph (B)
    print(f"[2/3] Building call graph ({len(artifact.functions)} functions)...")
    cg = CallGraph.from_artifact(artifact)

    # 3. Pick functions and refine with LLM
    picked = pick_smallest_functions(cg, args.num_functions)
    if not picked:
        print("ERROR: no functions with pseudo-C found. Use backend=ghidra_headless for real decompilation.", file=sys.stderr)
        return 1

    print(f"[3/3] Refining {len(picked)} functions with model={args.model}...")
    client = OpenAI(api_key=api_key, base_url=OPENCODE_GO_BASE_URL)

    for i, (name, original) in enumerate(picked, 1):
        print(f"\n{'='*70}")
        print(f"Function {i}/{len(picked)}: {name}  ({len(original)} chars)")
        print(f"{'='*70}")
        print("--- Original (Ghidra) ---")
        print(original)
        print()
        try:
            callers = cg.callers_of(name)
        except Exception:
            callers = set()
        try:
            refined = refine_function(client, args.model, name, original, callers)
        except Exception as e:
            print(f"ERROR refining {name}: {e}", file=sys.stderr)
            continue
        print(f"--- Refined ({args.model}) ---")
        print(refined)

    return 0


if __name__ == "__main__":
    sys.exit(main())
