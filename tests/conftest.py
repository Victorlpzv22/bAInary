from pathlib import Path

import pytest


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """An isolated cache directory for a single test."""
    d = tmp_path / "bainary_cache"
    d.mkdir()
    return d
