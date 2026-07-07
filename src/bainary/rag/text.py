"""Text construction for function vectorization.

The text is what gets vectorized by the `TextualVectorizer` (hashing trick
by default). It uses pseudocode when available (richest signal) and falls
back to assembly so lief_capstone-only artifacts can still be indexed.
"""

from __future__ import annotations

from bainary.lift.artifact import Function

TEXT_VERSION = "v1"


def build_text(fn: Function) -> str:
    """Build a text representation of a function for vectorization.

    Returns an empty string if the function has neither pseudocode
    nor assembly.
    """
    header = f"Function: `{fn.name}`  (sig: {fn.signature})\n"

    if fn.pseudocode:
        return header + fn.pseudocode
    if fn.assembly:
        return header + "// no decompilation available\n" + fn.assembly
    return ""
