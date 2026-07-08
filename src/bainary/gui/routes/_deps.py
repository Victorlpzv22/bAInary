"""Lazy access to the per-process ArtifactSession.

Route modules import :func:`get_session` instead of reaching for a global.
This indirection keeps route modules testable: tests can construct an app
(with :func:`bainary.gui.server.create_app`) and reach its session via
``request.app.state.session``.
"""

from __future__ import annotations

from fastapi import Request

from bainary.gui.state import ArtifactSession


def get_session(request: Request) -> ArtifactSession:
    """Return the :class:`ArtifactSession` attached to the running app."""
    sess = request.app.state.session
    assert isinstance(sess, ArtifactSession)
    return sess
