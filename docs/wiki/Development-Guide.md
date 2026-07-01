# Development Guide

Development setup, pre-commit hooks, CI, and testing conventions.

## Prerequisites

- Python 3.11+
- Java 21+ (for Ghidra backend)
- Ghidra 11.x (optional, for slow tests and decompilation)

## Setup

```bash
git clone <repo> bAInary
cd bAInary
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Pre-commit hooks

Every commit runs these checks automatically. If any fails, the commit is blocked.

```bash
# Install hooks
pre-commit install

# Run all hooks on demand
pre-commit run --all-files

# Bypass hooks (emergency only)
git commit --no-verify -m "..."
```

### Hook list

| Hook | What it checks |
|---|---|
| `trailing-whitespace` | No spaces at end of lines |
| `end-of-file-fixer` | Files end with newline |
| `check-yaml` | Valid YAML syntax |
| `check-added-large-files` | No files > 500KB |
| `ruff` | Lint + auto-fix |
| `ruff-format` | Code formatting |
| `mypy` | Type checking (strict mode) |
| `pytest (fast lane)` | All tests without Ghidra pass |

## CI (GitHub Actions)

Four jobs run on push and pull request:

| Job | When | What it runs |
|---|---|---|
| `lint-type` | Every push | `ruff check`, `ruff format --check`, `mypy src` |
| `test-fast` | Every push | `pytest -m "not slow"` + lief_capstone smoke test |
| `test-slow` | push to `dev` + PRs | Full `pytest` suite with Ghidra (cached, ~2 min) |
| `dependency-scan` | Every push | `pip-audit` for known CVEs |

## Test conventions

### Markers

- **Default**: Fast tests (<1s), no Ghidra, no network, no API keys.
- **`@pytest.mark.slow`**: Tests that need Ghidra (real decompilation). Skipped when `GHIDRA_HOME` is not set.

```bash
# Run fast tests (default in pre-commit)
pytest -m "not slow"

# Run everything (needs GHIDRA_HOME)
pytest

# Run only slow tests
pytest -m slow
```

### D tests

All D tests use `MockClient` — no API keys, no network, deterministic. Test the LLM integration path with:

```bash
python scripts/poc_llm.py tests/fixtures/loops_elf64/loops.elf
```

### Snapshot tests

Golden files in `tests/snapshots/` track the expected output of Ghidra's decompilation. Regenerate after intentional changes:

```bash
pytest tests/test_snapshot.py --update-snapshots -m slow
git diff tests/snapshots/  # review changes
git commit -a -m "update snapshots"
```

### Writing tests

```python
# Good: uses MockClient (fast, deterministic)
from bainary.refine import MockClient, Refiner

def test_my_feature(tmp_path):
    mock = MockClient(responses={"main": "refined code"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    result = refiner.refine(artifact)
    assert "refined" in result.functions[0].pseudocode
```

## Code style

- **Linter**: `ruff` with `select = ["E", "F", "I", "B", "UP", "W"]`
- **Formatter**: `ruff format` (line length 100)
- **Types**: `mypy --strict` with overrides for stub-less modules (`lief`, `capstone`, `typer`, `openai`, `anthropic`)
- **Docstrings**: Required on public classes and methods
- **Imports**: Sorted by `ruff isort` (stdlib, third-party, local)

## Type checking exceptions

Modules without type stubs use targeted overrides in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["lief", "capstone", "typer", "openai", "anthropic"]
ignore_missing_imports = true
```

Files with unavoidable `Any` return types use `# mypy: ignore-errors` at the top:

```python
# mypy: ignore-errors
"""Module that uses dynamic APIs (openai, anthropic, copy.deepcopy)."""
```

## Making a release

```bash
# Bump version in pyproject.toml
# Update README
# Tag
git tag v0.1.0
git push origin dev --tags
```
