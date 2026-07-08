// ASM panel — Monaco readOnly, language: plaintext (we pass raw assembly text).

let _editor = null;
let _currentAddr = null;

export async function init() {
  // Lazy-load Monaco to keep initial page weight small.
  try {
    const monaco = await import("monaco-editor");
    _editor = monaco.editor.create(document.getElementById("asm-body"), {
      value: "",
      language: "asm",
      readOnly: true,
      theme: "vs-dark",
      minimap: { enabled: false },
      fontSize: 12,
      automaticLayout: true,
      wordWrap: "off",
      scrollBeyondLastLine: false,
    });
    window.monaco = monaco; // expose for diff editor
  } catch (e) {
    const el = document.getElementById("asm-body");
    if (el) el.textContent = `Monaco no cargó: ${e.message}\n¿Internet disponible?`;
    console.error("[bAInary] asm Monaco init error:", e);
    throw e;
  }
}

export async function load(bus, address) {
  if (!_editor) await init();
  _currentAddr = address;
  try {
    const r = await fetch(`/api/functions/${encodeURIComponent(address)}`);
    if (!r.ok) {
      _editor.setValue(`// error: ${r.status}\n`);
      return;
    }
    const fn = await r.json();
    _editor.setValue(fn.assembly || "// sin assembly");
  } catch (e) {
    _editor.setValue(`// error: ${e.message}`);
  }
}

export function currentAddress() { return _currentAddr; }
