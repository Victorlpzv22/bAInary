from pathlib import Path

from bainary.lift.artifact import BinaryArtifact
from bainary.lift.cache import ArtifactCache


def _sample_artifact_dict() -> dict:
    return {
        "schema_version": "1.0",
        "binary": {
            "path": "/tmp/x.elf",
            "sha256": "ab" * 32,
            "format": "ELF",
            "arch": "x64",
            "endianness": "little",
            "entry_point": "0x400000",
            "base_address": "0x400000",
        },
        "sections": [],
        "imports": [],
        "exports": [],
        "strings": [],
        "functions": [],
    }


def test_cache_miss_returns_none(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    assert cache.lookup("nonexistent_sha") is None


def test_cache_store_and_lookup(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())
    cache.store("deadbeef" + "00" * 28, artifact)
    hit = cache.lookup("deadbeef" + "00" * 28)
    assert hit is not None
    assert hit.binary.format == "ELF"


def test_cache_invalidation_on_ghidra_version_change(tmp_cache_dir: Path):
    cache_v11 = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())
    cache_v11.store("cafebabe" + "00" * 28, artifact)

    cache_v12 = ArtifactCache(tmp_cache_dir, ghidra_version="12.0")
    assert cache_v12.lookup("cafebabe" + "00" * 28) is None


def test_cache_corruption_returns_none_and_cleans_up(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    sha = "12345678" + "00" * 28
    path = cache._path_for(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not valid json")

    assert cache.lookup(sha) is None
    assert not path.exists()


def test_cache_path_for_uses_sharded_layout(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    path = cache._path_for("ab" * 32)
    # Should be inside tmp_cache_dir and end in .json
    assert path.is_relative_to(tmp_cache_dir)
    assert path.suffix == ".json"


def test_cache_clear_removes_all_entries(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())
    cache.store("a" * 64, artifact)
    cache.store("b" * 64, artifact)
    cache.clear()
    assert cache.lookup("a" * 64) is None
    assert cache.lookup("b" * 64) is None


def test_cache_lru_eviction(tmp_cache_dir: Path):
    """When max_entries is exceeded, oldest entries are evicted."""
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0", max_entries=3)
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())

    # Store 3 entries
    for i in range(3):
        cache.store(chr(ord("a") + i) * 64, artifact)
    assert cache.count() == 3

    # Access the first entry to make it recently used
    import time

    time.sleep(0.05)  # ensure mtime differs
    cache.lookup("a" * 64)

    # Store a 4th entry — should evict the least-recently-accessed
    time.sleep(0.05)
    cache.store("d" * 64, artifact)
    assert cache.count() == 3
    # "a" was accessed recently, so it should survive
    assert cache.lookup("a" * 64) is not None
    # One of b or c was evicted (the older one)
    # Since we stored a, b, c in order and only touched a,
    # b is the oldest → evicted
    assert cache.lookup("b" * 64) is None
    assert cache.lookup("c" * 64) is not None
    assert cache.lookup("d" * 64) is not None


def test_cache_no_eviction_when_max_is_zero(tmp_cache_dir: Path):
    """max_entries=0 disables eviction."""
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0", max_entries=0)
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())
    for i in range(10):
        cache.store(chr(ord("a") + i) * 64, artifact)
    assert cache.count() == 10


def test_cache_count(tmp_cache_dir: Path):
    cache = ArtifactCache(tmp_cache_dir, ghidra_version="11.0")
    assert cache.count() == 0
    artifact = BinaryArtifact.from_dict(_sample_artifact_dict())
    cache.store("a" * 64, artifact)
    assert cache.count() == 1
    cache.store("b" * 64, artifact)
    assert cache.count() == 2
