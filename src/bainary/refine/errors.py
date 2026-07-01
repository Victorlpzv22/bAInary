"""Exception hierarchy for the bAInary refinement subsystem."""

from bainary.lift.errors import BainaryError


class RefineError(BainaryError):
    """Base for all refinement-related errors (LLM failure, config error, etc.)."""
