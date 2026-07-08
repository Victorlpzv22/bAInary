"""Tests for bainary.gui.routes.settings — GET/PUT .env."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Use tmp_path as the cwd so .env writes don't pollute the repo."""
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_get_settings_default(client: TestClient) -> None:
    r = client.get("/api/settings")
    assert r.status_code == 200
    s = r.json()
    assert s["llm_provider"] == "mock"
    assert s["has_key"] is False
    assert s["lift_backend"] == "ghidra_headless"
    # The masked key should be empty (no real key)
    assert s["api_key_masked"] == ""


def test_put_persists_and_invalidates(client: TestClient) -> None:
    # First, set LLM_MODEL via PUT
    r = client.put("/api/settings", json={"LLM_MODEL": "glm-5.2", "LLM_PROVIDER": "openai"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["llm_model"] == "glm-5.2"
    assert j["llm_provider"] == "openai"
    # .env file now exists and contains the new values
    env = Path.cwd() / ".env"
    assert env.exists()
    txt = env.read_text()
    assert "glm-5.2" in txt
    assert "openai" in txt


def test_put_with_key_persists_masked(client: TestClient) -> None:
    r = client.put("/api/settings", json={"OPENCODE_APIKEY": "sk-secret"})
    assert r.status_code == 200
    j = r.json()
    assert j["has_key"] is True
    assert j["api_key_masked"] == "sk-***"
    # raw key NOT echoed
    assert "sk-secret" not in str(j)
    # but it IS in .env (real value, masked only in the API response)
    env = Path.cwd() / ".env"
    assert "sk-secret" in env.read_text()


def test_put_unknown_key_422(client: TestClient) -> None:
    r = client.put("/api/settings", json={"EVIL_KEY": "x"})
    assert r.status_code == 422
    assert "EVIL_KEY" in r.json()["detail"]


def test_put_invalid_port_422(client: TestClient) -> None:
    r = client.put("/api/settings", json={"GUI_PORT": "not-a-number"})
    assert r.status_code == 422


def test_put_preserves_existing_keys(client: TestClient, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# keep me\nLLM_MODEL=old\n")
    r = client.put("/api/settings", json={"LLM_PROVIDER": "openai"})
    assert r.status_code == 200
    txt = env.read_text()
    assert "# keep me" in txt
    assert "openai" in txt


def test_put_invalidates_session_refiner(client: TestClient) -> None:
    sess = client.app.state.session
    sess.refiner = object()  # any non-None sentinel
    client.put("/api/settings", json={"LLM_MODEL": "new"})
    assert sess.refiner is None


def test_put_invalidates_session_index(client: TestClient) -> None:
    sess = client.app.state.session
    sess.index = object()
    client.put("/api/settings", json={"LLM_MODEL": "new"})
    assert sess.index is None


def test_get_settings_reflects_put(client: TestClient) -> None:
    client.put("/api/settings", json={"LLM_MODEL": "gpt-4o", "LLM_PROVIDER": "openai"})
    r = client.get("/api/settings")
    assert r.json()["llm_model"] == "gpt-4o"
    assert r.json()["llm_provider"] == "openai"
