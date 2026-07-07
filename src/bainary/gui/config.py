"""Configuration for the bAInary GUI.

The GUI reuses the .env conventions already used by the CLI helpers of
subsystems A/D: lift backend selection, LLM provider/model/key, and
the GUI host/port. Keys are read with `python-dotenv` and written with
`dotenv.set_key` (which preserves comments and unrelated variables).

RAG (subsystem C) needs **no** env config — it uses a local
`HashingTextVectorizer` without any API key.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, set_key

DEFAULTS: dict[str, str] = {
    "LIFT_BACKEND": "ghidra_headless",
    "LLM_PROVIDER": "mock",
    "OPENCODE_APIKEY": "",
    "LLM_MODEL": "kimi-k2.7-code",
    "LLM_BASE_URL": "https://opencode.ai/zen/go/v1",
    "GUI_HOST": "127.0.0.1",
    "GUI_PORT": "8787",
}

_DEFAULT_PATH = Path(".env")

# Keys that may legitimately appear in the .env file but are not directly
# consumed by the GUI's Settings view (e.g. GHIDRA_HOME stays in the env so
# the lift subsystem picks it up; we just don't expose it through this API).
_ADJUNCT_KEYS: tuple[str, ...] = ("GHIDRA_HOME",)


def _default_location() -> Path:
    return Path.cwd() / _DEFAULT_PATH


@dataclass
class Settings:
    """Resolved GUI settings derived from .env + DEFAULTS."""

    lift_backend: str
    llm_provider: str
    api_key: str
    llm_model: str
    llm_base_url: str
    gui_host: str
    gui_port: int

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def to_public_dict(self) -> dict[str, object]:
        """Return a JSON-safe dict with the API key masked."""
        return {
            "lift_backend": self.lift_backend,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "api_key_masked": mask_key(self.api_key),
            "has_key": self.has_api_key,
            "gui_host": self.gui_host,
            "gui_port": self.gui_port,
        }


def load_env(path: Path | None = None) -> Settings:
    """Load settings from a .env file (or DEFAULTS if missing).

    Missing keys fall back to :data:`DEFAULTS`. Empty .env values are
    treated like missing keys so the defaults still win.
    """
    p = Path(path) if path is not None else _default_location()
    vals = dict(DEFAULTS)
    if p.exists():
        for k, v in dotenv_values(p).items():
            if v is None:
                continue
            if v == "":
                # An explicit empty value (e.g. OPENCODE_APIKEY=) wins as "no key"
                if k in {"OPENCODE_APIKEY"}:
                    vals[k] = ""
                continue
            vals[k] = v
    return Settings(
        lift_backend=vals["LIFT_BACKEND"],
        llm_provider=vals["LLM_PROVIDER"],
        api_key=vals["OPENCODE_APIKEY"],
        llm_model=vals["LLM_MODEL"],
        llm_base_url=vals["LLM_BASE_URL"],
        gui_host=vals["GUI_HOST"],
        gui_port=int(vals["GUI_PORT"]),
    )


def save_env(path: Path | None, updates: dict[str, str | None]) -> None:
    """Persist `updates` into a .env file, preserving comments and other keys.

    `None` values are skipped (no write), matching the convention that
    the GUI only persists fields the user actually edited.
    """
    p = Path(path) if path is not None else _default_location()
    if not p.exists():
        p.write_text("")
    for k, v in updates.items():
        if v is None:
            continue
        set_key(str(p), k, v)


def mask_key(value: str) -> str:
    """Return a masked representation of an API key for display."""
    return "sk-***" if value else ""


__all__ = ["Settings", "load_env", "save_env", "mask_key", "DEFAULTS", "_ADJUNCT_KEYS"]
