from pathlib import Path

import pytest


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """An isolated cache directory for a single test."""
    d = tmp_path / "bainary_cache"
    d.mkdir()
    return d


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate golden snapshot files instead of comparing against them.",
    )


@pytest.fixture
def update_snapshots(request) -> bool:
    return bool(request.config.getoption("--update-snapshots"))


@pytest.fixture
def snapshot_dir() -> Path:
    d = Path(__file__).resolve().parent / "snapshots"
    d.mkdir(exist_ok=True)
    return d
