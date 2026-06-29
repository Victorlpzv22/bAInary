"""Exception hierarchy for the bAInary graph subsystem."""

from bainary.lift.errors import BainaryError


class GraphError(BainaryError):
    """Base for all graph-related errors (node not found, corrupt graph, etc.)."""
