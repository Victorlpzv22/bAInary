# bAInary — Subsistema E (GUI) Design Spec

**Estado:** Aprobado por el usuario (brainstorming completado el 2026-07-07)
**Fecha:** 2026-07-07
**Autor:** brainstormed with opencode (usuario: propietario de bAInary)
**Alcance:** Subsistema E únicamente — la interfaz visual de bAInary. Fuera de alcance: empaquetado Tauri (fase 2 optativa), edición persistente del pseudo-C, multi-sesión.

---

## 1. Contexto y objetivos

Los subsistemas **A** (`bainary.lift`), **B** (`bainary.graph`), **C** (`bainary.rag`) y **D** (`bainary.refine`) están implementados. La pieza que falta es **E**: una GUI que reúna la potencia de los cuatro subsistemas en una experiencia integrada tipo VS Code / Cursor.

**Hecho real en C (corregido durante brainstorming):** la implementación actual de RAG usa un `TextualVectorizer` local (hashing trick, `HashingTextVectorizer(dim=1024)`) — **sin API key, sin red**. La spec original de C mencionaba `EmbeddingClient`/`OpenAICompatibleEmbeddings`, pero el refactor `2dfe593` lo sustituyó por vectorización local. La GUI hereda esta simplicidad: el panel RAG funciona offline sin configuración.

**Goal de E:** una web app local servida por FastAPI en `http://127.0.0.1:8787`, abrible con `bainary-gui`, que permita:

1. Cargar un binario (file upload o ruta local) y ejecutar `lift()` desde la UI.
2. Visualizar árbol de funciones, grafo de llamadas interactivo (B), imports/exports/strings.
3. Ver cada función side-by-side: **ASM** (Monaco readOnly) | **Código reconstruido** (Monaco con pestañas Original/Refinado/Diff).
4. Disparar `Refiner.refine_one` por función o por lote, con progreso en vivo por SSE.
5. Construir un índice RAG local y buscar funciones similares en el artifact, sin API key.

**Stack decidido:** FastAPI backend + HTML/JS vanilla (sin bundler, sin framework) + Monaco editor via CDN (esm.sh) + vis-network via CDN. Empaquetado en `[gui]` extras, opcional.

---

## 2. Decisiones bloqueadas durante el brainstorming

| Decisión | Elección | Razón |
|---|---|---|
| Plataforma | Web app local (FastAPI + JS vanilla) | "Más parecido a Cursor/VS Code" → Monaco es el motor de VS Code; web local es lo más cercano sin instalar Rust/Electron |
| Editor de código | Monaco (via CDN esm.sh) | Mismo motor que VS Code: syntax highlighting, minimap, diff nativo, virtual scroll |
| Entregable | Fase 1: web local. Fase 2 opcional: empaquetar con Tauri | Menor riesgo; mismo frontend reutilizable |
| Alcance funcional | Visor + invocar lift/refine/RAG desde la UI | Reutiliza los 4 subsistemas; el usuario es novato en RE pero quiere control total |
| Presentación del código | Pestañas Original \| Refinado + botón Diff | Patrón familiar (Git diff VS Code); ahorra ancho vs side-by-side permanente |
| Hex panel | Oculto por defecto, toggle topbar abre como overlay flotante | El usuario lo escondería; ancho central se dedica a ASM + código |
| Fuente de bytes hex | Raw del fichero en disco vía `binary.path`; fallback `instruction.bytes` si el fichero no existe | Robusto ante known issue de basic_blocks vacíos en Ghidra 11.3.2 |
| Vistas adicionales v1 | Árbol funciones, grafo B, consola, RAG, Imports/Exports/Strings | Cobertura completa; cada una es poco código |
| Entrada del binario | Ambos: upload multipart o ruta local | Flexibilidad; valida formato con LIEF antes del lift |
| Config LLM | `.env` + dialog en UI que lo escribe | Ya usado por CLI; sin almacén nuevo |
| Build frontend | Sin build: HTML+JS vanilla, Monaco via CDN | Cero Node toolchain, arrancable con `pip install -e ".[gui]"` |

---

## 3. Disposición de módulos

```
src/bainary/gui/
├── __init__.py            # re-exports: serve(), create_app()
├── __main__.py            # python -m bainary.gui → uvicorn (argparse: host, port, --no-browser)
├── server.py              # create_app() FastAPI: rutas, lifespan, StaticFiles
├── state.py               # ArtifactSession + JobStatus (uno por proceso server)
├── config.py              # load_env() / save_env() con python-dotenv (mascarado)
├── errors.py              # GuiError(BainaryError)
├── routes/
│   ├── __init__.py
│   ├── binary.py          # POST /api/lift/{upload|path}, GET /api/binary, /api/hex, /api/functions
│   ├── functions.py       # GET /api/functions/{addr}, callers, callees
│   ├── refine.py          # POST /api/refine, GET /api/refine/result/{addr}, SSE events
│   ├── graph.py           # GET /api/graph, /api/graph/focus/{addr}
│   ├── rag.py             # POST /api/rag/build, /api/rag/search, /api/rag/similar
│   └── settings.py        # GET/PUT /api/settings
└── static/
    ├── index.html         # shell + grid layout + importmap (Monaco, vis-network vía CDN)
    ├── styles.css         # grid 2×2 + variables --sidebar-w, --bottom-h, --accent
    ├── app.js             # bootstrap, router de paneles, EventSource SSE
    └── panels/
        ├── functionTree.js
        ├── hex.js                  # opcional, abre como overlay
        ├── asm.js
        ├── code.js                 # Monaco pestañas Original/Refinado + diff
        ├── graph.js                # vis-network
        ├── rag.js
        ├── strings.js              # imports/exports/strings
        └── console.js              # SSE log
```

**Nuevo entry point en `pyproject.toml`:**
```toml
bainary-gui = "bainary.gui.__main__:main"
```

**Jerarquía de excepciones:**
```
BainaryError (lift/errors.py)
└── GuiError (gui/errors.py)
```

---

## 4. API REST

REST simple JSON sobre `http://127.0.0.1:8787`. **Single-tenant**, sin auth, escucha solo en loopback por defecto. Una `ArtifactSession` por proceso.

### 4.1 Lift & binario

| Método | Ruta | Body/Query | Respuesta |
|---|---|---|---|
| `POST` | `/api/lift/upload` | `multipart: file` + `?backend=` | `{job_id}` |
| `POST` | `/api/lift/path` | `{path, backend}` | `{job_id}` |
| `GET`  | `/api/binary` | — | `BinaryInfo` + secciones |
| `GET`  | `/api/hex` | `?addr=0x..&len=256` | `{addr, rows:[{off, hex, ascii}]}` |
| `GET`  | `/api/functions` | `?q=&filter=thunk\|extern` | `[{address, name, is_thunk, size_bytes}]` |

Subir fichero copia a `tmpdir` del proceso; ambos endpoints validan formato con LIEF síncrono (`422 unsupported format` si no es PE/ELF/Mach-O x86/x64/arm/arm64) y disparan lift asíncrono vía `loop.run_in_executor(None, lift, path, backend)`. Si `backend=ghidra_headless` y `GHIDRA_HOME` no set → `503`.

### 4.2 Función individual

| `GET` | `/api/functions/{addr}` | — | `Function` completa |
| `GET` | `/api/functions/{addr}/callees` | `?transitive=false` | `[{address, name}]` |
| `GET` | `/api/functions/{addr}/callers` | `?transitive=false` | `[{address, name}]` |

### 4.3 Refine (D)

| `POST` | `/api/refine` | `{addresses, min_size, skip_thunks}` | `{job_id}` |
| `GET`  | `/api/refine/result/{addr}` | — | `{refined}` o 404 |
| `SSE`  | `/api/events` | — | evento `refine.progress {addr, status}` |

### 4.4 Grafo (B)

| `GET` | `/api/graph` | — | `{nodes, edges}` |
| `GET` | `/api/graph/focus/{addr}` | `?depth=1` | subgrafo N-hops |

### 4.5 RAG (C)

| `POST` | `/api/rag/build` | — | `{count}` (crea `Index(HashingTextVectorizer())` + `add_artifact`) |
| `POST` | `/api/rag/search` | `{query, k=10}` | `[{score, function, source}]` |
| `POST` | `/api/rag/similar` | `{addr, k=10}` | idem |

RAG usa vectorización local — **no requiere** settings de provider/key/dim.

### 4.6 Meta

| `GET` | `/api/imports` `?q=` | — | lista filtrable |
| `GET` | `/api/exports` `?q=` | — | idem |
| `GET` | `/api/strings` `?q=` | — | idem |

### 4.7 Settings

| `GET` | `/api/settings` | — | `{provider, model, base_url, has_key, lift_backend}` (clave mascarada) |
| `PUT` | `/api/settings` | `{...}` | persiste `.env`, invalida `refiner` |

### 4.8 Estáticos

`/` sirve `static/index.html`; `/static/*` sirve el resto. Monaco y vis-network cargados desde `https://esm.sh/...` vía `<script type="importmap">`. Sin proxy backend.

### Decisiones transversales

- **No auth, single-tenant, loopback.** `host` configurable; default `127.0.0.1`.
- **Lift y refine asíncronos** vía `asyncio.create_task` + `loop.run_in_executor`. Ghidra subprocess es blocking pero no asfixia el event loop.
- **Errores:** JSON `{detail, field?}`, códigos 400/404/422/503. Sin stack traces al navegador.
- **Sin WebSocket.** SSE hace todo (logs unidireccionales server→client), reconexión nativa del navegador.

---

## 5. Layout de la UI

```
┌─────────────────────────────────────────────────────────────────┐
│ Topbar: [logo]  ▣ Abrir binario  [⊲ Hex off]   ⚙ Settings         │
├──────────┬────────────────────────────────────────────┬──────────┤
│ Sidebar  │  Workspace central (2 paneles)             │  Graph   │
│ Árbol    │  ┌─────────────────┬─────────────────────┐ │  (B)     │
│          │  │      ASM        │     CÓDIGO          │ │          │
│ ⊟ main   │  │  (Monaco        │ (Monaco, pestañas)  │ │ vis-     │
│ ⊟ add    │  │   readOnly)      │ [Original][Refinado] │ │ network  │
│  c       │  │                  │ [Diff]              │ │          │
│  mul     │  │  push rbp       │  int main(void){...}│ │ hops=1   │
│ ⊟ printf │  └─────────────────┴─────────────────────┘ │          │
│ 🔎 filter│                                             │          │
├──────────┴────────────────────────────────────────────┴──────────┤
│ [Console] [Imports] [Exports] [Strings] [RAG search]              │
└──────────────────────────────────────────────────────────────────┘
```

### Layout mechanics
- **CSS Grid 2×2** (`grid-template-areas`); sidebar, central, graph, inferior. Handles redimensionables nativos (`mousedown` + `mousemove` escribiendo CSS var `--sidebar-w`, `--bottom-h`).
- **3 instancias Monaco** (ASM, Original, Refinado/Diff) comparten worker; ~10MB memoria. `ResizeObserver` nativo dispara `editor.layout()`.
- **Diff view** se monta al clicar `[Diff]` usando `monaco.editor.createDiffEditor`; si `session.refined_cache[addr]` no existe → toast "Refina primero".

### Sidebar — Árbol de funciones
- Lista virtualizada manual (`IntersectionObserver` lazy-render) para >500 funciones.
- Header con input `🔎` filter (machea `name`).
- Fila: icono (thunk/extern/fn) + `name` + `address` + `size_bytes`. Hover → tooltip con signature.
- Click → carga función en paneles centrales. Click derecho → menú contextual ("Refinar", "Buscar similares en RAG", "Ver callers/callees").

### Hex panel (overlay opcional)
- Por defecto oculto. Toggle topbar abre como **overlay flotante** sobre el workspace central.
- Columnas `offset | 16 bytes hex | ASCII`. Pagination `PGUp/PGDn` → `GET /api/hex?addr=&len=512`. Input "Go to 0x…" arriba.
- Click byte ↔ highlight ASM bidireccional (lookup por `instruction.address`).

### ASM (Monaco readOnly, `language: "asm"`)
- Renderiza `Function.assembly`. Sincronización bidireccional con Hex cuando esté visible.

### Código (Monaco)
- 2 pestañas: `[Original]` (readOnly, Ghidra) `[Refinado]` (readOnly en v1, editable en post-MVP) y toggle `[Diff]`.
- Toolbar por panel: `⚙ Refinar` (single), `⚙ Refinar todo` (lote filtrado).

### Grafo (`graph.js`)
- **vis-network** via CDN esm.sh. Layout force-directed (toggle top-down). Nodes por tipo (thunk gris, externo naranja, fn azul, activo rojo).
- Click nodo → carga función en paneles centrales (igual que sidebar).
- Slider `depth` 1-3 controla `GET /api/graph/focus/{addr}?depth=N`.

### Panel inferior (tabs)
- **Console:** subscribida a `/api/events` SSE. Líneas con timestamp + tag `[lift]/[refine]/[rag]`.
- **Imports/Exports/Strings:** tablas con filter `?q=`, click → salta a address en Hex overlay.
- **RAG search:** input de texto → `POST /api/rag/search`. Si `Index` no existe → botón "Construir índice" → `POST /api/rag/build`. Hits mostrados con barra de score normalizada; click abre la Function.

### Topbar
- "Abrir binario": dialog con `<input type=file>` o `<input type=text>` ruta + dropdown backend (ghidra/lief).
- "Settings": dialog modal con campos `provider`, `api_key` (password), `base_url`, `model`, `lift_backend`. GET al mount, PUT al save.

### Tema y atajos
- Tema oscuro heredado de Monaco (`vs-dark`). CSS var `--accent` para highlights.
- `Ctrl+P` quick-open functions, `Ctrl+Shift+F` enfoca RAG search, `Escape` cierra dialogs.

---

## 6. Backend state y flujos

### State (`state.py`)

```python
@dataclass
class ArtifactSession:
    artifact: BinaryArtifact | None = None
    callgraph: CallGraph | None = None
    refiner: Refiner | None = None
    index: Index | None = None
    binary_bytes: bytes | None = None    # cache raw, leído perezoso de binary.path
    refined_cache: dict[str, str] = field(default_factory=dict)  # addr -> pseudocódigo refinado
    jobs: dict[str, JobStatus] = field(default_factory=dict)

@dataclass
class JobStatus:
    job_id: str
    kind: Literal["lift", "refine", "rag_build"]
    status: Literal["running", "done", "error"]
    progress: int = 0
    total: int = 0
```

- `loop.run_in_executor(None, fn)` envuelve llamadas blocking (`lift`, `refine_one`, `Index.add_artifact`).
- `.env` reload: `PUT /api/settings` invalida `refiner` e `index`; `artifact`/`callgraph` no.
- `binary_bytes` lee perezoso la 1.ª vez que toca `/api/hex` si `binary.path` existe; si no → 404.

### Flujo lift
1. POST /api/lift/{upload|path} → crea `JobStatus(lift)` → `asyncio.create_task` ejecuta `lift(path, backend)` en executor.
2. Progreso publicado en SSE como `lift.progress` / `log` (mensajes Ghidra subprocess filtrados).
3. On done: `session.artifact = artifact`, `session.callgraph = CallGraph.from_artifact(artifact)`, `session.binary_bytes = None`. SSE `lift.done {summary}`. Frontend refresca sidebar+graph.
4. On error: SSE `lift.error {detail}`. Toast + console.

### Flujo refine (single / batch)
1. POST /api/refine `{addresses, ...}` → `JobStatus(refine, total=len(addresses))`.
2. Executor: `refiner = _ensure_refiner()` (lazy, según settings), itera `addresses`:
   - `refined_code = refiner.refine_one(fn, callgraph)` — **método nuevo a añadir en D** (ver §10).
   - `session.refined_cache[addr] = refined_code`.
   - SSE `refine.progress {addr, status: "ok"|"skip"|"error"}`.
3. Frontend, al recibir `refine.progress` para la addr activa, hace `GET /api/refine/result/{addr}` y actualiza tab `[Refinado]`.
4. "Refinar todo" = `addresses = [f.address for f in artifact.functions if pasa filtros]`. Botón "Stop" marca el job como cancelado (no mata nada en vuelo).

### Flujo Diff
El frontend construye `monaco.editor.createDiffEditor` con `original = artifact.fns[addr].pseudocode` y `modified = session.refined_cache[addr]`. Sin llamada backend.

### Flujo RAG build & search
1. POST /api/rag/build → executor: `Index(HashingTextVectorizer(), InMemoryStore())` + `add_artifact(session.artifact)`. SSE `rag_build.done {count}`. `session.index = index`.
2. POST /api/rag/search `{query, k}` → si `session.index is None` → `409 "build index first"`. Ejecuta `index.search` en executor, devuelve hits.
3. POST /api/rag/similar `{addr, k}` → similar usando `session.artifact.fns[addr]`.

### SSE design
- `sse-starlette` `EventSourceResponse`. Una `asyncio.Queue` por cliente; broadcaster publica a todas las queues activas.
- Eventos: `lift.progress`, `lift.done`, `lift.error`, `refine.progress`, `refine.done`, `rag_build.done`, `log` (substring de stdout stderr de Ghidra filtrado). Frontend filtra por `event.type`.

---

## 7. Settings y `.env`

### `.env` completo (escrito por `PUT /api/settings`)

```bash
# Lift
LIFT_BACKEND=ghidra_headless        # o lief_capstone
GHIDRA_HOME=/home/victor/tools/ghidra_11.3.2_PUBLIC

# Refine (D)
LLM_PROVIDER=openai                 # openai | anthropic | mock
OPENCODE_APIKEY=sk-...              # mascarada en GET /api/settings
LLM_MODEL=kimi-k2.7-code
LLM_BASE_URL=https://opencode.ai/zen/go/v1

# GUI
GUI_HOST=127.0.0.1
GUI_PORT=8787
```

**Sin configuración de RAG** — C usa vectorización local, no requiere keys ni provider.

`config.py`:
- `load_env()` al arranque con `python-dotenv`.
- `save_env(updates)` usa `dotenv.set_key()` para preservar comentarios y variables externas.
- `GET /api/settings` mascara `OPENCODE_APIKEY` como `sk-***` (muestra `has_key: bool`).
- Tras `PUT /api/settings`: `session.refiner = None; session.index = None` (se recrean en la próxima llamada). No reinicia el server.

---

## 8. Dependencias

### Nuevas (en `[project.optional-dependencies].gui`)

```toml
gui = [
    "fastapi>=0.110",
    "uvicorn>=0.30",
    "sse-starlette>=1.8",
    "python-multipart>=0.0.9",
    "python-dotenv>=1.0",
]
```

Instalar con `pip install -e ".[gui]"`. Subsistemas A/B/C/D arrastran sus deps ya presentes. No se tocan las deps runtime del base.

### Sin bundling JS

- Monaco: `<script type="importmap">` apuntando a `https://esm.sh/monaco-editor@0.50/min/vs`. Navegador cachea tras primera carga. Requiere internet la primera vez. Vendoring offline: post-MVP.
- vis-network: `https://esm.sh/vis-network@9/...`. Idem.

### Tests

- `tests/test_gui.py` con `httpx` + `pytest-asyncio`. Smoke tests sobre `TestClient` de FastAPI. ~15 tests cubren endpoints, state lifecycle, SSE event publishing. Sin navegador, sin `@pytest.mark.slow`.

---

## 9. Cambios en D necesarios para la GUI

Añadir en `bainary.refine.Refiner`:

```python
def refine_one(self, fn: Function, cg: CallGraph | None = None) -> str | None:
    """Refine a single function's pseudo-C and return the refined code.
    Returns None when the function is filtered out or has no pseudo-C.
    Uses the same cache, filters, and prompt logic as refine().
    """
```

- `Refiner.refine()` se refactoriza para iterar `_refine_one` y ensamblar el nuevo artifact.
- Cero cambio de comportamiento público; tests D existentes no se rompen. Se añaden tests nuevos para `refine_one` (TDD).

---

## 10. Criterios de aceptación

1. `pip install -e ".[gui]"` funciona limpio en venv.
2. `bainary-gui` abre navegador en `127.0.0.1:8787` y muestra la shell vacía (sidebar, topbar, panel inferior).
3. Subir/pegar ruta de `tests/fixtures/loops_elf64/loops.elf` → lift vía UI (lief_capstone instantáneo) → árbol de funciones poblado, grafo visible, pestañas inferiores con imports/exports/strings.
4. Click en función → ASM (Monaco readOnly) y pseudo-C Original (Monaco) side-by-side.
5. Click "Refinar" en función con pseudo-C (requiere `LLM_PROVIDER=mock` o API key) → SSE progress → tab Refinado se actualiza → `[Diff]` abre diffEditor con diferencias rojo/verde. Con `LLM_PROVIDER=mock` todo funciona sin red ni API key.
6. Tab RAG → "Construir índice" → `search "loop sum"` devuelve hits ordenados por score → click en hit abre la función.
7. Settings dialog cambia `LLM_MODEL` y persiste en `.env`; al refinar siguiente usa el nuevo modelo sin reiniciar server.
8. `pytest -m "not slow"` pasa (incluye los nuevos ~15 tests GUI, todos fast lane).
9. `ruff check src tests` y `mypy src` pasan limpios.
10. `README.md` y `docs/wiki/` actualizan: `E` movido a "done", nueva página `Subsystem-E-GUI.md`, `Home.md` con enlace, `Architecture.md` con el nuevo subsistema en el diagrama + dependencias + `gui/` en el árbol.

---

## 11. Post-MVP (documentado, no abordado en v1)

- Empaquetado Tauri (fase 2 optativa; mismo frontend reutilizable).
- Edición inline del pseudo-C refinado + persistencia (`PUT /api/functions/{addr}/pseudocode`).
- Cancelación limpia de lift subprocess (señal al hijo Ghidra).
- Hex editor editable.
- Vendoring offline de Monaco y vis-network.
- `NumpyFileStore` persistente para RAG entre reinicios del server (solo activarlo: cambiar `InMemoryStore()` por `NumpyFileStore(root=...)` en `routes/rag.py`).
- Drag function → RAG similar search.
- Multi-binario / multi-sesión.

---

## 12. Actualizaciones al repo

1. Crear `src/bainary/gui/` con la estructura de §3 (13 archivos fuente + 8 estáticos).
2. Añadir `[project.optional-dependencies].gui` en `pyproject.toml` (ver §8).
3. Añadir entry point `bainary-gui = "bainary.gui.__main__:main"`.
4. Refactor `bainary.refine.Refiner` para añadir `refine_one` (§9) + tests nuevos.
5. Crear `tests/test_gui.py`.
6. Actualizar `README.md`:
   - Mover "E — GUI" de "What's not done" a "What's done".
   - Añadir sección **Library usage → Subsystem E — GUI** con ejemplo `bainary-gui`.
   - Mencionar `pip install -e ".[gui]"`.
7. Actualizar `docs/wiki/Architecture.md`:
   - Mover E de "(future)" a su celda activa en el diagrama ASCII.
   - Añadir `gui/` al árbol `src/bainary/`.
   - Añadir `GuiError` a la jerarquía de excepciones.
   - Añadir las dependencias de `[gui]`.
8. Crear `docs/wiki/Subsystem-E-GUI.md` con la guía de uso y patrones.
9. Actualizar `docs/wiki/Home.md` con el enlace y el estado a ✅.