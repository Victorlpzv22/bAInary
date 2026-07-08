// Code panel — Monaco readOnly, tabs: Original|Refinado|Diff.

let _editor = null;
let _diffEditor = null;
let _view = "original";
let _current = { address: null, name: null, original: "", refined: "" };

export async function init() {
  try {
    const monaco = await import("monaco-editor");
    _editor = monaco.editor.create(document.getElementById("code-body"), {
      value: "",
      language: "c",
      readOnly: true,
      theme: "vs-dark",
      minimap: { enabled: false },
      fontSize: 12,
      automaticLayout: true,
    });
  } catch (e) {
    const el = document.getElementById("code-body");
    if (el) el.textContent = `Monaco no cargó: ${e.message}\n¿Internet disponible?`;
    console.error("[bAInary] code Monaco init error:", e);
    throw e;
  }
}

export async function load(bus, address, name) {
  if (!_editor) await init();
  _current.address = address;
  _current.name = name || "?";
  try {
    const r = await fetch(`/api/functions/${encodeURIComponent(address)}`);
    if (!r.ok) {
      _current.original = `// error: ${r.status}`;
      _current.refined = "";
    } else {
      const fn = await r.json();
      _current.original = fn.pseudocode || "";
    }
  } catch (e) {
    _current.original = `// error: ${e.message}`;
    _current.refined = "";
  }
  // Fetch refined (may be 404 if not yet refined).
  await _fetchRefined(address);
  _applyView();
}

async function _fetchRefined(address) {
  try {
    const r = await fetch(`/api/refine/result/${encodeURIComponent(address)}`);
    if (r.ok) {
      const j = await r.json();
      _current.refined = j.refined || "";
    } else {
      _current.refined = "";
    }
  } catch {
    _current.refined = "";
  }
}

export function setView(name) {
  _view = name;
  _applyView();
}

function _applyView() {
  const body = document.getElementById("code-body");
  if (_view === "diff") {
    if (!_current.refined) {
      alert("Refina primero la función para ver el diff.");
      // Revert to original tab.
      document.querySelectorAll("#code-pane .tab").forEach(t => {
        t.setAttribute("aria-selected", t.dataset.tab === "original" ? "true" : "false");
      });
      _view = "original";
      _renderEditor();
      return;
    }
    const monaco = window.monaco;
    if (!_diffEditor) {
      _diffEditor = monaco.editor.createDiffEditor(body, {
        theme: "vs-dark",
        readOnly: true,
        automaticLayout: true,
        renderSideBySide: true,
      });
    }
    const orig = monaco.editor.createModel(_current.original || "// original", "c");
    const mod = monaco.editor.createModel(_current.refined || "// refinado", "c");
    _diffEditor.setModel({ original: orig, modified: mod });
  } else {
    _renderEditor();
  }
}

function _renderEditor() {
  if (_diffEditor) {
    _diffEditor.dispose();
    _diffEditor = null;
  }
  if (!_editor) return;
  if (_view === "refined") {
    if (!_current.refined) {
      _editor.setValue(`// (no refinado aún; click "Refinar" para ejecutar el LLM)`);
    } else {
      _editor.setValue(_current.refined);
    }
  } else {
    _editor.setValue(_current.original || `// ${_current.name ?? "..."}`);
  }
}

export function currentAddress() { return _current.address; }
