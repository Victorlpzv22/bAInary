"""Exception hierarchy for the bAInary RAG subsystem."""

from bainary.lift.errors import BainaryError


class RagError(BainaryError):
    """Base for all RAG-related errors (embedding failure, store error, config error)."""
