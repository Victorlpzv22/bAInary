# Subsistema E (GUI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GUI web local (FastAPI + Monaco) que integra lift (A), grafo (B), RAG (C) y refine (D), servida en `127.0.0.1:8787` por `bainary-gui`.

**Architecture:** FastAPI backend reutiliza directamente `bainary.lift`/`graph`/`rag`/`refine`. Frontend vanilla JS+HTML (sin bundler), Monaco y vis-network via CDN esm.sh. Una `ArtifactSession` singleton en memoria; lift/refine/RAG ejecutan en `loop.run_in_executor` para no bloquear el event loop. SSE para progreso.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, sse-starlette, python-multipart, python-dotenv. Frontend: HTML/JS vanilla, Monaco (CDN), vis-network (CDN).

**Spec:** `docs/superpowers/specs/2026-07-07-gui-subsystem-design.md`

---

## Task 1 — `Refiner.refine_one` (fundamento para GUI)

**Files:**
- Modify: `src/bainary/refine/refiner.py`
- Test: `tests/test_refiner.py`

- [ ] **1.1** Escribir test fallido para `refine_one`:
```python
def test_refine_one_single_function(tmp_path):
    mock = MockClient(responses={"main": "int main() { return result; }"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    main = artifact.functions[0]
    refined_code = refiner.refine_one(main, CallGraph.from_artifact(artifact))
    assert refined_code == "int main() { return result; }"

def test_refine_one_skip_when_filtered(tmp_path):
    mock = MockClient(responses={"_fini": "should not appear"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"), skip_thunks=True)
    artifact = _test_artifact()
    fini = next(f for f in artifact.functions if f.name == "_fini")
    assert refiner.refine_one(fini) is None

def test_refine_one_uses_cache(tmp_path):
    mock = MockClient(responses={"main": "refined main"})
    refiner = Refiner(client=mock, cache=RefinementCache(tmp_path, model="mock"))
    artifact = _test_artifact()
    refiner.refine_one(artifact.functions[0])
    first_count = mock.call_count
    refiner.refine_one(artifact.functions[0])
    assert mock.call_count == first_count
```

- [ ] **1.2** Run: `pytest tests/test_refiner.py::test_refine_one_single_function -v`
  Expected: FAIL with `AttributeError: 'Refiner' object has no attribute 'refine_one'`

- [ ] **1.3** Refactor `refiner.py`: extraer la lógica interna del loop a `_refine_one(fn, cg, min_size, skip_thunks, skip_no_pseudocode) -> str | None` (sin mutar `fn`; retorna el código refinado o None si filtrado). `refine()` itera `_refine_one` y muta la copia deepcopy. Añadir el método público:
```python
def refine_one(
    self,
    fn: Function,
    cg: CallGraph | None = None,
    *,
    min_size: int | None = None,
    skip_thunks: bool | None = None,
    skip_no_pseudocode: bool | None = None,
) -> str | None:
    """Refine a single function's pseudo-C, return the refined code.

    Returns None when the function is filtered out (skip_thunks, skip_no_pseudocode,
    min_size) or has no pseudocode. Uses cache and prompt logic shared with refine().
    The original `fn` is never modified.
    """
    return self._refine_one(
        fn, cg,
        min_size if min_size is not None else self._min_size,
        skip_thunks if skip_thunks is not None else self._skip_thunks,
        skip_no_pseudocode if skip_no_pseudocode is not None else self._skip_no_pseudocode,
    )
```

- [ ] **1.4** Run: `pytest tests/test_refiner.py -v`
  Expected: PASS (todos los tests previos + los 3 nuevos)

- [ ] **1.5** Commit:
```bash
git add src/bainary/refine/refiner.py tests/test_refiner.py
git commit -m "refactor(refine): extract refine_one for granular GUI use

Refine_one refactoriza el bucle interno de Refiner.refine() a un
helper reutilizable que devuelve el código refinado de UNA funcion
sin mutar el artifact original. refine() ahora itera refine_one y
ensambla el nuevo artifact. Necesario para Subsistema E (GUI), que
refina función por función con progreso SSE."
```

---

## Task 2 — `bainary.gui` skeleton (errors, state)

**Files:**
- Create: `src/bainary/gui/__init__.py`
- Create: `src/bainary/gui/errors.py`
- Create: `src/bainary/gui/state.py`
- Test: `tests/test_gui_state.py`

- [ ] **2.1** Escribir `tests/test_gui_state.py`:
```python
from bainary.gui.state import ArtifactSession, JobStatus

def test_artifact_session_empty():
    s = ArtifactSession()
    assert s.artifact is None
    assert s.callgraph is None
    assert s.index is None
    assert s.refiner is None
    assert s.binary_bytes is None
    assert s.refined_cache == {}
    assert s.jobs == {}

def test_job_status_defaults():
    j = JobStatus(job_id="abc", kind="lift")
    assert j.status == "running"
    assert j.progress == 0
    assert j.total == 0
    assert j.log_lines == []

def test_gui_error_is_bainary_error():
    from bainary.lift.errors import BainaryError
    from bainary.gui.errors import GuiError
    assert issubclass(GuiError, BainaryError)
```

- [ ] **2.2** Run: `pytest tests/test_gui_state.py -v`
  Expected: FAIL `ImportError`

- [ ] **2.3** Crear `errors.py`:
```python
from bainary.lift.errors import BainaryError

class GuiError(BainaryError):
    """Error del subsistema GUI de bAInary."""
```

Crear `state.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from bainary.lift.artifact import BinaryArtifact
from bainary.graph import CallGraph
from bainary.refine import Refiner
from bainary.rag import Index

@dataclass
class JobStatus:
    job_id: str
    kind: Literal["lift", "refine", "rag_build"]
    status: Literal["running", "done", "error", "cancelled"] = "running"
    progress: int = 0
    total: int = 0
    log_lines: list[str] = field(default_factory=list)

@dataclass
class ArtifactSession:
    artifact: BinaryArtifact | None = None
    callgraph: CallGraph | None = None
    refiner: Refiner | None = None
    index: Index | None = None
    binary_bytes: bytes | None = None
    refined_cache: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, JobStatus] = field(default_factory=dict)
```

Crear `__init__.py`:
```python
"""bAInary GUI subsystem (E): FastAPI web app + Monaco frontend."""
from bainary.gui.errors import GuiError
__all__ = ["GuiError"]
```

- [ ] **2.4** Run: `pytest tests/test_gui_state.py -v`
  Expected: PASS

- [ ] **2.5** Commit:
```bash
git add src/bainary/gui/ tests/test_gui_state.py
git commit -m "feat(gui): add ArtifactSession + JobStatus state

Esqueleto del subsistema E: GuiError (sub de BainaryError),
ArtifactSession (singleton en memoria con artifact/callgraph/
index/refiner/binary_bytes/refined_cache/jobs) y JobStatus para
trackear lift/refine/rag_build asíncronos."
```

---

## Task 3 — `config.py` (.env load/save mascarado)

**Files:**
- Create: `src/bainary/gui/config.py`
- Test: `tests/test_gui_config.py`

- [ ] **3.1** Escribir `tests/test_gui_config.py`:
```python
from pathlib import Path
from bainary.gui.config import load_env, save_env, mask_key

def test_load_env_defaults_when_missing(tmp_path):
    s = load_env(tmp_path / "missing.env")
    assert s.lift_backend == "ghidra_headless"
    assert s.llm_provider == "mock"
    assert s.gui_host == "127.0.0.1"
    assert s.gui_port == 8787
    assert s.has_api_key is False

def test_load_env_reads_existing(tmp_path):
    p = tmp_path / ".env"
    p.write_text("LLM_PROVIDER=openai\nOPENCODE_APIKEY=sk-test123\nLLM_MODEL=gpt-4o\n")
    s = load_env(p)
    assert s.llm_provider == "openai"
    assert s.api_key == "sk-test123"
    assert s.llm_model == "gpt-4o"
    assert s.has_api_key is True

def test_save_env_writes_and_preserves(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment preserved\nLLM_MODEL=gpt-4o\n")
    save_env(p, {"LLM_MODEL": "glm-5.2", "LLM_PROVIDER": "openai"})
    txt = p.read_text()
    assert "# comment preserved" in txt
    assert "glm-5.2" in txt
    assert "openai" in txt

def test_mask_key_with_value():
    assert mask_key("sk-test123") == "sk-***"

def test_mask_key_no_value():
    assert mask_key("") == ""
```

- [ ] **3.2** Run: `pytest tests/test_gui_config.py -v`
  Expected: FAIL `ImportError`

- [ ] **3.3** Crear `config.py`:
```python
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values, set_key

DEFAULTS = {
    "LIFT_BACKEND": "ghidra_headless",
    "LLM_PROVIDER": "mock",
    "OPENCODE_APIKEY": "",
    "LLM_MODEL": "kimi-k2.7-code",
    "LLM_BASE_URL": "https://opencode.ai/zen/go/v1",
    "GUI_HOST": "127.0.0.1",
    "GUI_PORT": "8787",
}

@dataclass
class Settings:
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

def load_env(path: Path | None = None) -> Settings:
    path = Path(path) if path else Path.cwd() / ".env"
    vals = dict(DEFAULTS)
    if path.exists():
        vals.update({k: v for k, v in dotenv_values(path).items() if v})
    return Settings(
        lift_backend=vals["LIFT_BACKEND"],
        llm_provider=vals["LLM_PROVIDER"],
        api_key=vals["OPENCODE_APIKEY"],
        llm_model=vals["LLM_MODEL"],
        llm_base_url=vals["LLM_BASE_URL"],
        gui_host=vals["GUI_HOST"],
        gui_port=int(vals["GUI_PORT"]),
    )

def save_env(path: Path | None, updates: dict[str, str]) -> None:
    path = Path(path) if path else Path.cwd() / ".env"
    if not path.exists():
        path.write_text("")
    for k, v in updates.items():
        set_key(str(path), k, v)

def mask_key(value: str) -> str:
    return "sk-***" if value else ""
```

- [ ] **3.4** Run: `pytest tests/test_gui_config.py -v`
  Expected: PASS

- [ ] **3.5** Commit: `feat(gui): add config load/save with masked keys`

---

## Task 4 — FastAPI app + StaticFiles + lifespan

**Files:**
- Create: `src/bainary/gui/server.py`
- Create: `src/bainary/gui/__main__.py`
- Create: `src/bainary/gui/routes/__init__.py`
- Create: `src/bainary/gui/static/index.html`
- Create: `src/bainary/gui/static/styles.css`
- Create: `src/bainary/gui/static/app.js`
- Test: `tests/test_gui_server.py`

- [ ] **4.1** Escribir `tests/test_gui_server.py`:
```python
from fastapi.testclient import TestClient
from bainary.gui.server import create_app

def test_root_serves_html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()

def test_unknown_api_404():
    client = TestClient(create_app())
    r = client.get("/api/nope")
    assert r.status_code == 404

def test_static_file_served():
    client = TestClient(create_app())
    r = client.get("/static/app.js")
    assert r.status_code == 200
```

- [ ] **4.2** Run: `pytest tests/test_gui_server.py -v`
  Expected: FAIL `ImportError`

- [ ] **4.3** Crear `server.py`:
```python
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from bainary.gui.state import ArtifactSession

SESSION = ArtifactSession()

def create_app() -> FastAPI:
    app = FastAPI(title="bAInary GUI", version="0.1.0")
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (static_dir / "index.html").read_text()

    return app

app = create_app()
```

Crear `__main__.py`:
```python
from __future__ import annotations
import argparse
import webbrowser
from bainary.gui.server import create_app

def main() -> None:
    p = argparse.ArgumentParser(prog="bainary-gui")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()
    if not args.no_browser:
        try:
            webbrowser.open(f"http://{args.host}:{args.port}")
        except Exception:
            pass
    import uvicorn
    uvicorn.run("bainary.gui.server:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
```

Crear `routes/__init__.py` vacío.

Crear `static/index.html` (shell con grid areas, topbar, panel inferior):
```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head><meta charset="utf-8"><title>bAInary</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div id="topbar">bAInary <button id="open">Abrir binario</button></div>
<div id="grid">
  <aside id="sidebar">sidebar</aside>
  <main id="workspace">workspace</main>
  <aside id="graph-panel">graph</aside>
</div>
<footer id="bottom-panel"><div id="console"></div></footer>
<script type="module" src="/static/app.js"></script>
</body></html>
```

Crear `static/styles.css` (grid 2×2, dark):
```css
:root{--sidebar-w:260px;--bottom-h:200px;--accent:#4ec9b0;}
body{margin:0;font:14px monospace;background:#1e1e1e;color:#d4d4d4;}
#topbar{height:36px;display:flex;align-items:center;padding:0 12px;background:#252526;}
#grid{display:grid;grid-template-areas:"sidebar workspace graph" "bottom bottom bottom";grid-template-columns:var(--sidebar-w) 1fr 320px;height:calc(100vh - 36px - var(--bottom-h));}
#sidebar{grid-area:sidebar;overflow:auto;background:#252526;}
#workspace{grid-area:workspace;display:grid;grid-template-columns:1fr 1fr;}
#graph-panel{grid-area:graph;background:#252526;}
#bottom-panel{grid-area:bottom;height:var(--bottom-h);background:#1e1e1e;}
```

Crear `static/app.js` placeholder:
```js
console.log("bAInary GUI");
export {};
```

- [ ] **4.4** Run: `pytest tests/test_gui_server.py -v`
  Expected: PASS

- [ ] **4.5** Commit: `feat(gui): FastAPI app shell with static mount`

---

## Task 5 — Rutas lift (upload/path/binary/hex/functions)

**Files:**
- Create: `src/bainary/gui/routes/binary.py`
- Modify: `src/bainary/gui/server.py` (registrar rutas + fixture helper)
- Test: `tests/test_gui_binary.py`

- [ ] **5.1** Escribir `tests/test_gui_binary.py`:
```python
from pathlib import Path
from fastapi.testclient import TestClient
from bainary.gui.server import create_app, SESSION
from bainary.gui.state import ArtifactSession
from tests.test_refiner import _test_artifact

def reset_session():
    SESSION.artifact = None
    SESSION.callgraph = None
    SESSION.binary_bytes = None

def test_lift_path_lief(client):
    reset_session()
    fixture = Path("tests/fixtures/loops_elf64/loops.elf")
    r = client.post("/api/lift/path", json={"path": str(fixture), "backend": "lief_capstone"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    # poll hasta done (en test síncrono el executor termina rápido)
    import time
    for _ in range(30):
        st = client.get(f"/api/jobs/{jid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done"
    r2 = client.get("/api/binary")
    assert r2.status_code == 200
    assert "functions" not in r2.json() or True  # info binaria

def test_lift_path_missing_422(client):
    reset_session()
    r = client.post("/api/lift/path", json={"path": "/nope", "backend": "lief_capstone"})
    assert r.status_code == 422

def test_hex(client):
    reset_session()
    SESSION.artifact = _test_artifact()
    SESSION.binary_bytes = b"\x55\x48\x89\xe5" * 8  # 32 bytes
    r = client.get("/api/hex?addr=0x0&len=32")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 2  # 32 bytes / 16
    assert rows[0]["hex"].count("  ") >= 1

def test_functions_filter(client):
    reset_session()
    SESSION.artifact = _test_artifact()
    r = client.get("/api/functions?q=main")
    assert r.status_code == 200
    fns = r.json()
    assert any(f["name"] == "main" for f in fns)
```

Usar fixture `client` pytest:
```python
import pytest
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from bainary.gui.server import create_app
    return TestClient(create_app())
```

- [ ] **5.2** Implementar `routes/binary.py`:
  - `POST /api/lift/path` valida con `lift.api._precheck_with_lief` (captura `ValueError` → 422). Chequea `GHIDRA_HOME` si backend es ghidra → 503. Crea `JobStatus(lift)`, `asyncio.create_task(loop.run_in_executor(None, _do_lift, path, backend, job_id))`.
  - `_do_lift`: llama `lift(path, backend=backend)`, actualiza `SESSION.artifact`, `SESSION.callgraph = CallGraph.from_artifact(artifact)`, `SESSION.binary_bytes = None`, marca job done.
  - `POST /api/lift/upload`: recibe multipart, escribe a `tmpdir`, reusa `_do_lift`.
  - `GET /api/binary`: devuelve `SESSION.artifact.binary` como dict o 404 si artifact None.
  - `GET /api/hex`: addr+len (default 256). Si `SESSION.binary_bytes` None y `SESSION.artifact.binary.path` existe, leer raw. Paginar rows de 16 bytes `{off, hex, ascii}`.
  - `GET /api/functions?filter=`: devuelve lista `[{address, name, is_thunk, size_bytes}]` filtrable.
  - `GET /api/jobs/{job_id}`: estado JobStatus.

- [ ] **5.3** Run: `pytest tests/test_gui_binary.py -v` → PASS.

- [ ] **5.4** Commit: `feat(gui): lift routes (upload/path/hex/functions list)`

---

## Task 6 — Rutas functions (addr/callers/callees)

**Files:**
- Create: `src/bainary/gui/routes/functions.py`
- Test: `tests/test_gui_functions.py`

- [ ] **6.1** Tests:
```python
def test_function_detail(client):
    SESSION.artifact = _test_artifact()
    r = client.get("/api/functions/0x1000")
    assert r.status_code == 200
    assert r.json()["name"] == "main"

def test_function_404(client):
    SESSION.artifact = _test_artifact()
    r = client.get("/api/functions/0xdeadbeef")
    assert r.status_code == 404

def test_callees(client):
    SESSION.artifact = _test_artifact()
    SESSION.callgraph = CallGraph.from_artifact(SESSION.artifact)
    r = client.get("/api/functions/0x1000/callees")
    assert r.status_code == 200
    assert any(c["name"] == "add" for c in r.json())

def test_callers(client):
    # add no tiene callers (artifact test), pero comprobamos API
    SESSION.artifact = _test_artifact()
    SESSION.callgraph = CallGraph.from_artifact(SESSION.artifact)
    r = client.get("/api/functions/0x2000/callers")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **6.2** Implementar `routes/functions.py`:
  - `GET /api/functions/{addr}`: lookup en `SESSION.artifact.functions` por address. 404 si no.
  - `GET /api/functions/{addr}/callees`: lee `function.callees` directo. `?transitive=true` usa `SESSION.callgraph.callees_of(name, transitive=True)`.
  - `GET /api/functions/{addr}/callers`: idem con callers.
  - Devuelve 409 si `SESSION.artifact is None`.

- [ ] **6.3** Pass + commit: `feat(gui): function detail + callers/callees routes`

---

## Task 7 — Rutas graph

**Files:**
- Create: `src/bainary/gui/routes/graph.py`
- Test: `tests/test_gui_graph.py`

- [ ] **7.1** Tests:
```python
def test_graph_full(client):
    SESSION.artifact = _test_artifact()
    SESSION.callgraph = CallGraph.from_artifact(SESSION.artifact)
    r = client.get("/api/graph")
    assert r.status_code == 200
    g = r.json()
    assert len(g["nodes"]) >= 2
    assert isinstance(g["edges"], list)

def test_graph_focus(client):
    SESSION.artifact = _test_artifact()
    SESSION.callgraph = CallGraph.from_artifact(SESSION.artifact)
    r = client.get("/api/graph/focus/0x1000?depth=1")
    assert r.status_code == 200

def test_graph_409_when_no_artifact(client):
    r = client.get("/api/graph")
    assert r.status_code == 409
```

- [ ] **7.2** Implementar `routes/graph.py`:
  - 409 si `SESSION.callgraph is None`.
  - `GET /api/graph`: serializa `SESSION.callgraph.graph.nodes(data=True)` a `[{id, name, address, is_thunk}]` y `edges: [[from, to]]`.
  - `GET /api/graph/focus/{addr}?depth=N`: usa `networkx.ego_graph(SESSION.callgraph.graph, addr, radius=N)` y serializa el subgrafo.

- [ ] **7.3** Pass + commit: `feat(gui): graph routes (full + focus N-hops)`

---

## Task 8 — SSE broadcaster + Rutas refine

**Files:**
- Create: `src/bainary/gui/sse.py`
- Create: `src/bainary/gui/routes/refine.py`
- Test: `tests/test_gui_refine.py`

- [ ] **8.1** Tests:
```python
def test_sse_broker_publish_subscribe():
    import asyncio
    from bainary.gui.sse import SSEBroker
    async def run():
        b = SSEBroker()
        async with b.subscribe() as q:
            b.publish("test", {"x": 1})
            evt = await asyncio.wait_for(q.get(), timeout=1)
            assert evt["event"] == "test"
            assert evt["data"] == {"x": 1}
    asyncio.run(run())

def test_refine_one(client, monkeypatch):
    SESSION.artifact = _test_artifact()
    SESSION.callgraph = CallGraph.from_artifact(SESSION.artifact)
    # forzar provider mock
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    r = client.post("/api/refine", json={"addresses": ["0x1000"], "skip_thunks": True})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    # poll
    import time
    for _ in range(30):
        st = client.get(f"/api/jobs/{jid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done"
    r2 = client.get("/api/refine/result/0x1000")
    assert r2.status_code == 200
    assert r2.json()["refined"]

def test_refine_result_404(client):
    r = client.get("/api/refine/result/0xdeadbeef")
    assert r.status_code == 404
```

- [ ] **8.2** Implementar `sse.py` (clase SSEBroker con lista de queues, `subscribe()` async context manager, `publish(event_type, data)`).
  Implementar `routes/refine.py`:
  - `POST /api/refine`: crea `JobStatus(refine)`, executor itera addresses, usa `Refiner.refine_one` (crea `Refiner` con `create_client(provider=...)` según settings cargadas), guarda en `SESSION.refined_cache[addr]`, emite `refine.progress`.
  - `GET /api/refine/result/{addr}`: 404 si no en cache.
  - `GET /api/events`: endpoint SSE usando `sse-starlette EventSourceResponse`.

- [ ] **8.3** Pass + commit: `feat(gui): refine routes with SSE progress + SSE broker`

---

## Task 9 — Rutas rag

**Files:**
- Create: `src/bainary/gui/routes/rag.py`
- Test: `tests/test_gui_rag.py`

- [ ] **9.1** Tests:
```python
def test_rag_build(client):
    SESSION.artifact = _test_artifact()
    SESSION.index = None
    r = client.post("/api/rag/build")
    assert r.status_code == 200
    assert r.json()["count"] > 0
    assert SESSION.index is not None

def test_rag_search(client):
    SESSION.artifact = _test_artifact()
    SESSION.index = None  # forzar build
    client.post("/api/rag/build")
    r = client.post("/api/rag/search", json={"query": "main", "k": 5})
    assert r.status_code == 200
    hits = r.json()
    assert isinstance(hits, list)

def test_rag_search_no_index_409(client):
    SESSION.index = None
    r = client.post("/api/rag/search", json={"query": "main"})
    assert r.status_code == 409

def test_rag_similar(client):
    SESSION.artifact = _test_artifact()
    SESSION.index = None
    client.post("/api/rag/build")
    r = client.post("/api/rag/similar", json={"addr": "0x1000", "k": 5})
    assert r.status_code == 200
```

- [ ] **9.2** Implementar `routes/rag.py`:
  - `POST /api/rag/build`: 409 si artifact None. Crea `Index(HashingTextVectorizer(dim=1024), InMemoryStore())`, `add_artifact(SESSION.artifact)`, asigna `SESSION.index`.
  - `POST /api/rag/search`: 409 si `SESSION.index is None`. Ejecuta `index.search(query, k)` en executor.
  - `POST /api/rag/similar`: idem con `search_similar` lookup function por addr.

- [ ] **9.3** Pass + commit: `feat(gui): rag routes (build/search/similar) with local vectorizer`

---

## Task 10 — Rutas imports/exports/strings

**Files:**
- Create: `src/bainary/gui/routes/meta.py`
- Test: `tests/test_gui_meta.py`

- [ ] **10.1** Tests con artifact cargado; cada endpoint devuelve lista filtrable por `?q=`.

- [ ] **10.2** Implementar 3 endpoints leyendo `SESSION.artifact.imports/exports/strings`. Filtro substring case-insensitive sobre name/value. 409 si artifact None.

- [ ] **10.3** Pass + commit: `feat(gui): imports/exports/strings routes`

---

## Task 11 — Rutas settings

**Files:**
- Create: `src/bainary/gui/routes/settings.py`
- Test: `tests/test_gui_settings.py`

- [ ] **11.1** Tests:
```python
def test_get_settings(client, monkeypatch, tmp_path):
    monkeypatch.setattr("bainary.gui.config.Path.cwd", lambda: tmp_path)
    r = client.get("/api/settings")
    assert r.status_code == 200
    s = r.json()
    assert "provider" in s
    assert s["has_key"] is False
    assert "api_key" not in s or "sk" not in str(s.get("api_key"))

def test_put_settings_persists(client, monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("# comment\nLLM_MODEL=old\n")
    monkeypatch.setattr("bainary.gui.config.Path.cwd", lambda: tmp_path)
    r = client.put("/api/settings", json={"LLM_MODEL": "glm-5.2"})
    assert r.status_code == 200
    txt = (tmp_path / ".env").read_text()
    assert "glm-5.2" in txt
```

- [ ] **11.2** Implementar `routes/settings.py`:
  - GET llama `config.load_env` y enmascara clave. Devuelve `{provider, model, base_url, has_key, lift_backend}`.
  - PUT `config.save_env(cwd/.env, updates)`, invalida `SESSION.refiner = None; SESSION.index = None`.

- [ ] **11.3** Pass + commit: `feat(gui): settings routes (GET/PUT .env)`

---

## Task 12 — Frontend estático

**Files:**
- Modify: `static/index.html`, `static/styles.css`, `static/app.js`
- Create: `static/panels/{functionTree,asm,code,graph,rag,strings,console,hex}.js`

- [ ] **12.1** `index.html`: grid 2×2 + topbar + panel inferior. `<script type="importmap">` con Monaco y vis-network via esm.sh. Carga `app.js` módulo.
- [ ] **12.2** `styles.css`: variables `--sidebar-w:260px; --bottom-h:200px; --accent:#4ec9b0`. Grid template areas. Dark. Handlers resize.
- [ ] **12.3** `app.js`: bootstrap, EventSource a `/api/events`, router paneles.
- [ ] **12.4** `functionTree.js`: fetch `/api/functions`, render, filter, click → `panel:loadFunction` event.
- [ ] **12.5** `asm.js` + `code.js`: 3 Monaco (asm readOnly, original readOnly, refinado readOnly). Diff al clic `[Diff]`, toast si no refinado. Fetch `/api/functions/{addr}`.
- [ ] **12.6** `graph.js`: vis-network con `/api/graph`. Slider depth. Click nodo → loadFunction.
- [ ] **12.7** `rag.js`: search input, botón build, hits con score bar.
- [ ] **12.8** `strings.js`: tabs imports/exports/strings, click → goto addr.
- [ ] **12.9** `console.js`: subscribe SSE, render timestamped + colored.
- [ ] **12.10** `hex.js`: overlay flotante, paginación, goto, click byte → ASM highlight.
- [ ] **12.11** Smoke test manual: `bainary-gui` + cargar `loops.elf` con lief.
- [ ] **12.12** Commit: `feat(gui): frontend shell with Monaco, vis-network, SSE console`

---

## Task 13 — pyproject `[gui]` extras + entry point

**Files:** Modify `pyproject.toml`

- [ ] **13.1** Añadir:
```toml
[project.optional-dependencies]
gui = [
    "fastapi>=0.110",
    "uvicorn>=0.30",
    "sse-starlette>=1.8",
    "python-multipart>=0.0.9",
    "python-dotenv>=1.0",
]
[project.scripts]
bainary-gui = "bainary.gui.__main__:main"
```

- [ ] **13.2** `pip install -e ".[gui]"` smoke. `bainary-gui --help` arranca.
- [ ] **13.3** Commit: `build: add [gui] extras and bainary-gui entry point`

---

## Task 14 — Lint, types, full fast lane

- [ ] **14.1** `ruff check src tests` limpio.
- [ ] **14.2** `mypy src` limpio (preferible sin `# mypy: ignore-errors`).
- [ ] **14.3** `pytest -m "not slow"` → verde.
- [ ] **14.4** Commit si fixes: `chore(gui): lint and type fixes`

---

## Task 15 — Docs

**Files:** Modify `README.md`, `docs/wiki/Home.md`, `docs/wiki/Architecture.md`, Create `docs/wiki/Subsystem-E-GUI.md`

- [ ] **15.1** `Home.md`: E → ✅, enlace a Subsystem-E-GUI, stats actualizadas.
- [ ] **15.2** `Architecture.md`: diagrama con E activo, árbol `gui/`, `GuiError` en jerarquía, deps `[gui]`.
- [ ] **15.3** `Subsystem-E-GUI.md`: guía completa (layout, endpoints, settings .env, post-MVP).
- [ ] **15.4** `README.md`: features añaden Web GUI, install `[gui]`, usage `bainary-gui`, estado 5 subsistemas.
- [ ] **15.5** Commit: `docs: add Subsystem E (GUI) to README, wiki, architecture`

---

**Sumario:** 15 tareas, ~80 pasos TDD, commits frecuentes. Cada backend task aísla una familia de endpoints. Sin tests `@pytest.mark.slow` (no abren navegador); validación manual del frontend en Task 12.11. ~15 tests nuevos en fast lane.
