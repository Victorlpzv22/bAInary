# CLI Reference

## `bainary-lift`

Lift a binary to a JSON artifact.

```bash
bainary-lift <binary> -o <output.json> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `binary` | Path to PE/ELF/Mach-O binary (required) |

### Options

| Option | Default | Description |
|---|---|---|
| `-o, --output` | — | Path to write JSON artifact (required) |
| `--backend` | `ghidra_headless` | Backend: `ghidra_headless` or `lief_capstone` |
| `--no-cache` | `False` | Skip the sha256 cache |
| `--timeout` | `600` | Backend timeout in seconds |
| `--verbose` / `-v` | `False` | Enable debug logging |
| `--help` | — | Show help and exit |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | bAInary error (backend failed, cache issue) |
| `2` | Input error (unsupported format, file not found) |
| `3` | I/O error (can't write output) |

### Examples

```bash
# Basic usage
bainary-lift target.exe -o target.json

# Use fast backend (no Ghidra, ASM only)
bainary-lift target.elf -o target.json --backend lief_capstone

# Force re-lift (skip cache)
bainary-lift target.elf -o target.json --no-cache

# Increase Ghidra timeout (default 10 min)
bainary-lift large_binary.elf -o large.json --timeout 1800

# Debug logging
bainary-lift target.elf -o target.json --verbose
```

## `python -m bainary.lift`

Same as `bainary-lift` (the proper entry point).

```bash
python -m bainary.lift target.exe -o target.json
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GHIDRA_HOME` | — | Path to Ghidra installation (required for `ghidra_headless`) |
| `BAINARY_CACHE_DIR` | `~/.cache/bainary/` | Override artifact cache location |
| `BAINARY_REFINE_CACHE_DIR` | `~/.cache/bainary/refine/` | Override refinement cache location |
| `OPENCODE_APIKEY` | — | API key for OpenCode Go (subsystem D) |
