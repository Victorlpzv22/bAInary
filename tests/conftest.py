import sys
from pathlib import Path

# Make `src/bainary` importable as `bainary` for tests without installing
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """An isolated cache directory for a single test."""
    d = tmp_path / "bainary_cache"
    d.mkdir()
    return d
