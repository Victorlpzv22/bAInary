"""bAInary GUI subsystem (E): FastAPI web app + Monaco frontend.

Re-exports the public surface of the subsystem. The FastAPI application
factory lives in :mod:`bainary.gui.server`; asynchronous backend state
lives in :mod:`bainary.gui.state`; per-request error handling relies on
:class:`bainary.gui.errors.GuiError`.
"""

from __future__ import annotations

from bainary.gui.errors import GuiError

__all__ = ["GuiError"]
