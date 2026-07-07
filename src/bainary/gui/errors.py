"""Exception hierarchy for the bAInary GUI subsystem."""

from __future__ import annotations

from bainary.lift.errors import BainaryError


class GuiError(BainaryError):
    """Error raised by the bAInary GUI subsystem.

    Subclasses :class:`bainary.lift.errors.BainaryError` so it propagates
    through any handler that catches the project-wide base error.
    """
