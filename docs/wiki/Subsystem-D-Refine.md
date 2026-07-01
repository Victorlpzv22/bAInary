# Subsystem D — Refine

LLM-based refinement of decompiled pseudo-C. Takes a `BinaryArtifact` (from A) and a `CallGraph` (from B), sends each function's pseudo-C to an LLM, and returns a **new** artifact with refined code. The original is never modified.

```
  BinaryArtifact  ──>  Refiner.refine()  ──>  new BinaryArtifact
       +                       │                    (unchanged original)
    CallGraph                  │
                              ├── For each function:
                              │   1. Filter (skip thunks, small functions, no-pseudo)
                              │   2. Build prompt (pseudo-C + callers/callees)
                              │   3. Check cache (sha256(pseudo + model + version))
                              │   4. Call LLM (or use cache hit)
                              │   5. Strip markdown fences
                              │   6. Store in cache
                              │
                              └── Return new artifact
```

## Public API

```python
from bainary.refine import Refiner, create_client

# 1. Create an LLM client (pick your provider)

# OpenCode Go → Kimi K2.7 Code
client = create_client(
    provider="openai",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="kimi-k2.7-code",
)

# OpenCode Go → MiniMax M3 (Anthropic-compatible)
client = create_client(
    provider="anthropic",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="minimax-m3",
)

# OpenAI direct
client = create_client(provider="openai", api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o")

# Anthropic direct
client = create_client(provider="anthropic", api_key=os.environ["ANTHROPIC_API_KEY"], model="claude-3-5-sonnet-20241022")

# 2. Refine
refiner = Refiner(client=client)
refined = refiner.refine(artifact, cg)

# With filters
refined = refiner.refine(artifact, cg, min_size=50, skip_thunks=True)

# Without call graph (no caller/callee context)
refined = refiner.refine(artifact)

# 3. Compare before/after
original_code = artifact.functions[0].pseudocode
refined_code  = refined.functions[0].pseudocode
```

## Filters

| Filter | Default | Effect |
|---|---|---|
| `min_size` | `0` | Skip functions with fewer bytes of machine code |
| `skip_thunks` | `True` | Skip PLT wrappers and import stubs |
| `skip_no_pseudocode` | `True` | Skip functions without decompilable pseudo-C |

Set defaults in the constructor: `Refiner(client, min_size=50, skip_thunks=True)`. Override per-call: `refiner.refine(artifact, min_size=0)`.

## Providers

| Provider | SDK needed | Endpoint format | Works with |
|---|---|---|---|
| `openai` | `openai>=1.0` | `/v1/chat/completions` | OpenAI, OpenCode Go (Kimi, GLM, DeepSeek, MiMo), Ollama |
| `anthropic` | `anthropic>=0.20` | `/v1/messages` | Anthropic, OpenCode Go (MiniMax, Qwen) |
| `mock` | None | None (deterministic) | Tests only 🧪 |

```python
# Temperature handling: some models (Kimi K2.7) reject temperature=0.
# The client auto-retries with temperature=1 on HTTP 400.
```

## Cache

```python
from bainary.refine.cache import RefinementCache

# Default: ~/.cache/bainary/refine/
cache = RefinementCache(model="kimi-k2.7-code")

# Custom location
from pathlib import Path
cache = RefinementCache(Path("/tmp/refine-cache"), model="kimi-k2.7-code")

# The cache key includes:
# - sha256(original_pseudo_c)
# - model name
# - PROMPT_VERSION (from prompts.py)
#
# Change any of these → cache invalidated.
```

## Refinement example

```
BEFORE (Ghidra):
  /* WARNING: Unknown calling convention */
  int main(void) {
    uint uVar1;
    int sum;
    int i;
    sum = 0;
    for (i = 0; i < 5; i = i + 1) {
      sum = add(sum,i);
    }
    uVar1 = mul(sum,2);
    printf("sum=%d, mul=%d\n",(ulong)(uint)sum,(ulong)uVar1);
    return 0;
  }

AFTER (LLM refined):
  /* Computes sum of 0..4 and prints it with its double */
  int main(void) {
    int sum = 0;
    for (int i = 0; i < 5; i++) {
      sum = add(sum, i);
    }
    int product = mul(sum, 2);
    printf("sum=%d, mul=%d\n", sum, product);
    return 0;
  }
```

Changes:
- `uVar1` → `product` (meaningful name)
- `/* WARNING: ... */` removed
- `(ulong)(uint)` casts removed
- `i++` instead of `i = i + 1`
- One-line comment added
- Dead variables (`b_local`, `a_local`) eliminated

## Error handling

| Scenario | Behaviour |
|---|---|
| API key missing | `RefineError` at client creation |
| LLM rate limit (429) | Auto-retry with exponential backoff (3 attempts) |
| Temperature rejected | Auto-retry with temperature=1 |
| One function fails | That function keeps original, others continue |
| Empty response | Function keeps original, `pseudocode_error` set |
| No functions match filters | Returns original artifact unchanged |

## Source files

| File | Responsibility |
|---|---|
| `refiner.py` | `Refiner` class — orchestrates iteration, prompts, calls, cache |
| `client.py` | `LLMClient` ABC + `OpenAICompatibleClient` + `AnthropicClient` + `MockClient` + `create_client()` |
| `prompts.py` | `build_prompt()` + `PROMPT_VERSION` constant |
| `cache.py` | `RefinementCache` — file-based cache with model/version invalidation |
| `errors.py` | `RefineError` exception |

## PoC script

`scripts/poc_llm.py` is a standalone proof-of-concept that predates the full `bainary.refine` subsystem. It covers the same pipeline (A+B+LLM) in a single self-contained script. The script is kept for ad-hoc use and debugging:

```bash
python scripts/poc_llm.py tests/fixtures/loops_elf64/loops.elf
```
