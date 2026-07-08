"""Tests for bainary.gui.server — FastAPI app factory + static mount."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_root_serves_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert "bAInary" in r.text or "bainary" in r.text.lower()


def test_unknown_api_404(client: TestClient) -> None:
    r = client.get("/api/nope")
    assert r.status_code == 404


def test_static_app_js_served(client: TestClient) -> None:
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "bAInary" in r.text or "console" in r.text


def test_static_styles_css_served(client: TestClient) -> None:
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert "--accent" in r.text or "background" in r.text


def test_create_app_returns_fastapi() -> None:
    from fastapi import FastAPI

    app = create_app()
    assert isinstance(app, FastAPI)


def test_app_has_session_state() -> None:
    # The module-level SESSION should be wired into the app state for handlers.
    from bainary.gui.server import create_app

    app = create_app()
    assert hasattr(app.state, "session")
    assert app.state.session is not None
    assert app.state.session.artifact is None  # starts empty
