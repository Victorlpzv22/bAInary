"""Prompt building for LLM refinement of decompiled pseudo-C."""

from __future__ import annotations

PROMPT_VERSION = "v1"


def build_prompt(
    function_name: str,
    pseudo_c: str,
    caller_names: list[str] | None = None,
    callee_names: list[str] | None = None,
) -> str:
    """Build the refinement prompt for one function.

    The prompt asks the LLM to:
    1. Rename anonymous variables (iVar1, auStack_8, etc.)
    2. Remove Ghidra's WARNING comments
    3. Fix the function signature
    4. Add a one-line comment
    5. Preserve the exact same behavior

    Output format: a single code block with the refined C.
    """
    callers = ", ".join(caller_names) if caller_names else "(unknown)"
    callees = ", ".join(callee_names) if callee_names else "(unknown)"

    return f"""You are a senior reverse engineer. Refine the following decompiled C function from a binary.

Function: `{function_name}`
Callers: {callers}
Callees: {callees}

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
