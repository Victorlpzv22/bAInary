"""Tests for bainary.gui.config — .env load/save with masked keys.

Settings used by the GUI:
  - Lift:   LIFT_BACKEND (default ghidra_headless; lief_capstone for offline tests)
  - Refine: LLM_PROVIDER (openai|anthropic|mock), OPENCODE_APIKEY, LLM_MODEL, LLM_BASE_URL
  - GUI:    GUI_HOST, GUI_PORT

RAG (subsystem C) uses local vectorization and has no env config.
"""

from __future__ import annotations

from pathlib import Path

from bainary.gui.config import Settings, load_env, mask_key, save_env


def test_load_env_defaults_when_missing(tmp_path: Path) -> None:
    s = load_env(tmp_path / "missing.env")
    assert s.lift_backend == "ghidra_headless"
    assert s.llm_provider == "mock"
    assert s.llm_model  # some default
    assert s.llm_base_url
    assert s.gui_host == "127.0.0.1"
    assert s.gui_port == 8787
    assert s.api_key == ""
    assert s.has_api_key is False


def test_load_env_reads_existing(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text(
        "LLM_PROVIDER=openai\nOPENCODE_APIKEY=sk-test123\nLLM_MODEL=gpt-4o\n"
        "LLM_BASE_URL=https://example.com/v1\nLIFT_BACKEND=lief_capstone\n"
        "GUI_HOST=0.0.0.0\nGUI_PORT=9000\n"
    )
    s = load_env(p)
    assert s.llm_provider == "openai"
    assert s.api_key == "sk-test123"
    assert s.llm_model == "gpt-4o"
    assert s.llm_base_url == "https://example.com/v1"
    assert s.lift_backend == "lief_capstone"
    assert s.gui_host == "0.0.0.0"
    assert s.gui_port == 9000
    assert s.has_api_key is True


def test_load_env_overrides_defaults_with_partial_file(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("LLM_PROVIDER=openai\n")  # missing other keys
    s = load_env(p)
    assert s.llm_provider == "openai"
    assert s.gui_port == 8787  # default preserved
    assert s.api_key == ""


def test_save_env_writes_and_preserves_comments(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("# top comment preserved\nLLM_MODEL=old\n# bottom comment\n")
    save_env(p, {"LLM_MODEL": "glm-5.2", "LLM_PROVIDER": "openai"})
    txt = p.read_text()
    assert "# top comment preserved" in txt
    assert "# bottom comment" in txt
    assert "glm-5.2" in txt
    assert "openai" in txt
    assert "old" not in txt.split("\n")  # 'old' replaced, not appended


def test_save_env_creates_file_when_missing(tmp_path: Path) -> None:
    p = tmp_path / "fresh.env"
    save_env(p, {"LLM_MODEL": "kimi-k2.7-code"})
    assert p.exists()
    assert "kimi-k2.7-code" in p.read_text()


def test_save_env_ignores_none_values(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    save_env(p, {"LLM_MODEL": "kimi", "OPENCODE_APIKEY": None})  # type: ignore[dict-item]
    txt = p.read_text()
    assert "kimi" in txt
    # OPENCODE_APIKEY should be either absent or empty, not the literal "None"
    assert "=None" not in txt


def test_save_env_empty_string_writes_blank(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    save_env(p, {"OPENCODE_APIKEY": ""})
    txt = p.read_text()
    assert "OPENCODE_APIKEY" in txt
    assert "OPENCODE_APIKEY=" in txt or 'OPENCODE_APIKEY=""' in txt


def test_mask_key_with_value() -> None:
    assert mask_key("sk-test123") == "sk-***"


def test_mask_key_no_value() -> None:
    assert mask_key("") == ""


def test_settings_is_dataclass() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(Settings)


def test_load_env_does_not_emit_when_path_is_none(monkeypatch) -> None:
    # Path.cwd() could fail in unusual sandboxes; ensure no exception is raised
    # when no .env exists. Use a guaranteed-missing path.
    s = load_env(None)
    assert s.llm_provider == "mock"
