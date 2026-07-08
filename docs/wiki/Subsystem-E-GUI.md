# Subsystem E — Web GUI

The bAInary GUI is a local web app that integrates all four upstream
subsystems (A: Lift, B: Graph, C: RAG, D: Refine) behind a Monaco-driven
SPA. The whole thing runs in a single FastAPI process bound to
`127.0.0.1:8787` by default.

## Quick start

```bash
pip install -e ".[gui]"
bainary-gui                          # opens http://127.0.0.1:8787
bainary-gui --port 9000 --no-browser
```

From the dialog, either upload a binary or paste a local path, then
choose `lief_capstone` (no Ghidra required, fast) or `ghidra_headless`
(requires `GHIDRA_HOME`, slow but most complete). The frontend
subscribes to `/api/events` (SSE) and the lifted artifact appears in
the sidebar within a second or two.

## Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ Topbar: [logo]  ▣ Abrir binario  [Hex off]   ⚙ Settings          │
├──────────┬────────────────────────────────────────────┬──────────┤
│ Sidebar  │  Workspace central (2 paneles por defecto) │  Graph   │
│ Árbol    │                                            │  (B)     │
│ de       │  ┌─────────────────┬─────────────────────┐ │          │
│ funciones│  │      ASM        │     CÓDIGO          │ │ vis-     │
│ (filter) │  │   (Monaco       │ (Monaco, pestañas)  │ │ network  │
│          │  │    readOnly)    │ [Original][Refinado]│ │          │
│          │  │                  │ [Diff]              │ │ hops=1   │
│          │  │  push rbp       │  int main(void){...}│ │          │
│          │  │  mov rdi, ...   │                      │ │          │
│          │  └─────────────────┴─────────────────────┘ │          │
├──────────┴────────────────────────────────────────────┴──────────┤
│ [Console] [Imports] [Exports] [Strings] [RAG search]               │
└──────────────────────────────────────────────────────────────────┘
```

- **Sidebar:** virtualized function list, `?` filter, drag-to-RAG.
- **Workspace (default 2 panels):** ASM (Monaco readOnly) | Code
  (Monaco, tabs Original|Refinado|Diff). Hex is a hidden overlay
  toggled from the topbar.
- **Graph panel:** `vis-network`, full graph on lift, N-hop focus on
  click. Hops slider 1-3.
- **Bottom panel:** Console (SSE log), Imports/Exports/Strings
  (filterable tables), RAG (build + search).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | server liveness |
| `POST` | `/api/lift/path` | lift binary at path (async, returns job_id) |
| `POST` | `/api/lift/upload` | upload + lift (multipart) |
| `GET`  | `/api/binary` | BinaryInfo + counts |
| `GET`  | `/api/hex` | hex rows, 16 bytes per row, paginated |
| `GET`  | `/api/functions` | function list, optional `?q=` filter |
| `GET`  | `/api/functions/{addr}` | full Function record (assembly, pseudo, CFG) |
| `GET`  | `/api/functions/{addr}/callees` | direct callees |
| `GET`  | `/api/functions/{addr}/callers` | direct callers |
| `GET`  | `/api/graph` | full call graph (nodes/edges) |
| `GET`  | `/api/graph/focus/{addr}?depth=N` | N-hop ego graph |
| `POST` | `/api/refine` | refine batch (SSE progress) |
| `GET`  | `/api/refine/result/{addr}` | refined pseudo-C (or 404) |
| `GET`  | `/api/events` | SSE stream (lift/refine/rag progress) |
| `POST` | `/api/rag/build` | build local RAG index |
| `POST` | `/api/rag/search` | natural-language search |
| `POST` | `/api/rag/similar` | find similar functions to a given address |
| `GET`  | `/api/settings` | public (key-masked) view of `.env` |
| `PUT`  | `/api/settings` | persist a partial update to `.env` |
| `GET`  | `/api/imports` / `/api/exports` / `/api/strings` | metadata |
| `GET`  | `/api/jobs/{job_id}` | background-job status |

## Configuration via `.env`

```bash
# Lift
LIFT_BACKEND=ghidra_headless        # or lief_capstone
GHIDRA_HOME=/home/victor/tools/ghidra_11.3.2_PUBLIC

# Refine (D)
LLM_PROVIDER=mock                   # openai | anthropic | mock
OPENCODE_APIKEY=sk-...              # masked in /api/settings
LLM_MODEL=kimi-k2.7-code
LLM_BASE_URL=https://opencode.ai/zen/go/v1

# RAG (C) — no env config needed; uses local hashing vectorizer

# GUI
GUI_HOST=127.0.0.1
GUI_PORT=8787
```

`PUT /api/settings` writes back with `dotenv.set_key`, preserving
comments and unrelated variables. The next request rebuilds the cached
`Refiner` and `Index` automatically.

## State model

A single `ArtifactSession` lives in `app.state.session`:

```python
@dataclass
class ArtifactSession:
    artifact: BinaryArtifact | None
    callgraph: CallGraph | None
    refiner: Refiner | None             # lazy, invalidated on PUT /settings
    index: Index | None                  # lazy, invalidated on PUT /settings
    binary_bytes: bytes | None           # cached hex view
    refined_cache: dict[str, str]        # addr -> refined pseudo-C
    jobs: dict[str, JobStatus]           # lift / refine / rag_build tracking
```

Lift and refine run on `loop.run_in_executor(None, ...)` so the event
loop stays responsive while Ghidra or the LLM is working. Progress is
fanned out to every connected browser tab via an `SSEBroker` on
`app.state.sse_broker`.

## Post-MVP

- Tauri packaging (windowed desktop app, no web server).
- Inline editing of the refined pseudo-C (persist back to artifact).
- Vendoring Monaco + vis-network for offline use.
- Persistent RAG index (`NumpyFileStore` is already implemented in
  subsystem C, just not wired into the GUI).
- Drag-from-sidebar → RAG similar search.
- Multi-binary sessions.
- Cancellation of long-running lift subprocesses.
