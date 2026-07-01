# Subsystem A — Lift

Binary parsing & lifting. The foundation: takes a compiled binary and produces a structured `BinaryArtifact` with every function, its assembly, pseudo-C, control flow graph, and metadata.

```
                  bainary.lift
    binary.exe  ──────────────>  BinaryArtifact (JSON + Python object)
                                      │
                                      ├── functions[i].assembly       (raw ASM)
                                      ├── functions[i].pseudocode     (Ghidra's decompiled C)
                                      ├── functions[i].cfg            (basic blocks + edges)
                                      ├── functions[i].callers        (who calls this function)
                                      ├── functions[i].callees        (what this function calls)
                                      ├── functions[i].stack_frame    (local variables)
                                      ├── sections                    (.text, .data, ...)
                                      ├── imports / exports
                                      └── strings
```

## Public API

```python
from bainary.lift import lift, BinaryArtifact, LifterError

# Lift a binary (default: ghidra_headless backend)
artifact = lift("target.exe")

# Use the fast backend (no Ghidra, ASM only)
artifact = lift("target.elf", backend="lief_capstone")

# Disable cache for fresh analysis
artifact = lift("target.exe", use_cache=False)

# Handle errors
try:
    artifact = lift("arm_binary.elf")
except ValueError as e:
    print(f"Unsupported: {e}")  # e.g. MIPS, RISC-V
except LifterError as e:
    print(f"Backend failed: {e}")
```

## Backends

| Backend | Decompilation | Speed | Dependencies |
|---|---|---|---|
| `ghidra_headless` (default) | ✅ Full pseudo-C | 10–30s per binary | Ghidra 11.x + Java 21+ |
| `lief_capstone` | ❌ ASM only | <1s per binary | LIEF + capstone |

### Architecture

```
LifterBackend (ABC)
├── GhidraHeadlessBackend   — spawns analyzeHeadless + Jython postScript
└── LiefCapstoneBackend     — LIEF for sections/imports, Capstone for ASM
```

To add a new backend, implement `LifterBackend` and register it in `backends/__init__.py`.

## BinaryArtifact fields

```python
artifact.binary.format              # "PE" | "ELF" | "MACHO"
artifact.binary.arch                # "x86" | "x64" | "arm" | "arm64"
artifact.binary.decompiler_version  # "ghidra-11.3.2" | "lief-capstone"
artifact.binary.sha256              # fingerprint for caching
artifact.binary.entry_point         # "0x401000"
artifact.binary.base_address        # "0x400000"

artifact.sections     # [Section(name, address, size, permissions), ...]
artifact.imports      # [ImportRef(address, name, library), ...]
artifact.exports      # [ExportRef(address, name), ...]
artifact.strings      # [StringRef(address, value, encoding), ...]
artifact.functions    # [Function(...), ...]
```

## Function fields

```python
fn = artifact.functions[0]

fn.address              # "0x401000"
fn.name                 # "main"
fn.signature            # "int main(void)"
fn.calling_convention   # "cdecl" | "stdcall" | "unknown"
fn.size_bytes           # bytes of machine code
fn.is_thunk             # True if PLT/got wrapper
fn.assembly             # multi-line ASM text
fn.pseudocode           # C-like decompilation (or None if failed)
fn.pseudocode_error     # error message if decompilation failed
fn.cfg                  # Cfg(nodes=[...], edges=[["a","b"], ...])
fn.basic_blocks         # [BasicBlock(address, instructions, successors, terminator)]
fn.callers              # [CallRef(address, name), ...]
fn.callees              # [CallRef(address, name, is_external), ...]
fn.stack_frame          # StackFrame(size, locals=[Local(...)])
```

## Supported formats & architectures

| Format | x86 | x64 | ARM | ARM64 |
|---|---|---|---|---|
| PE | ✅ | ✅ | — | — |
| ELF | ✅ | ✅ | ✅ | ✅ |
| Mach-O | ✅ | ✅ | ✅ | ✅ |

Unsupported: WASM, MIPS, RISC-V (raises `ValueError` with clear message).

## Cache

Artifacts are cached by sha256 at `$BAINARY_CACHE_DIR` (default `~/.cache/bainary/`). Sharded layout: `<root>/<sha[0:2]>/<sha[2:4]>/<sha>.json`. LRU eviction at 200 entries. Cache invalidates on Ghidra version change.

```python
artifact = lift("target.exe")        # caches automatically
artifact = lift("target.exe")        # cache hit: returns instantly (<0.5s)
artifact = lift("target.exe", use_cache=False)  # force re-lift
```

## CLI

```bash
# Lift and save to JSON
bainary-lift target.exe -o target.json

# Use fast backend
bainary-lift target.elf -o target.json --backend lief_capstone

# Debug logging
bainary-lift target.elf -o target.json --verbose
```

Exit codes: `1` = bAInary error, `2` = invalid input, `3` = I/O error.

## Source files

| File | Responsibility |
|---|---|
| `api.py` | `lift()` — orchestrator, pre-check, cache, error mapping |
| `artifact.py` | 13 dataclasses (BinaryArtifact, Function, BasicBlock, ...) |
| `schema.py` | 14 Pydantic models (JSON contract v1.0) |
| `cache.py` | `ArtifactCache` — sha256-keyed with LRU eviction |
| `errors.py` | `BainaryError`, `LifterError`, `SchemaValidationError` |
| `cli.py` | Typer CLI |
| `backends/base.py` | `LifterBackend` ABC + `BackendRegistry` |
| `backends/ghidra_headless.py` | Ghidra subprocess wrapper |
| `backends/lief_capstone.py` | LIEF + Capstone backend |
| `backends/postscript.py` | Jython 2.7 postScript (runs inside Ghidra JVM) |
