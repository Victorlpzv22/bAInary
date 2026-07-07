"""Text construction for function embeddings.

The text is what gets embedded by the EmbeddingClient. It uses
pseudocode when available (richest semantic signal) and falls back
to assembly so lief_capstone-only artifacts can still be indexed.
"""

from __future__ import annotations

from bainary.lift.artifact import Function

TEXT_VERSION = "v1"


def build_text(fn: Function) -> str:
    """Build a text representation of a function for embedding.

    Returns an empty string if the function has neither pseudocode
    nor assembly.
    """
    header = f"Function: `{fn.name}`  (sig: {fn.signature})\n"

    if fn.pseudocode:
        return header + fn.pseudocode
    if fn.assembly:
        return header + "// no decompilation available\n" + fn.assembly
    return ""
