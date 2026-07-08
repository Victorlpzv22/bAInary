// bAInary GUI bootstrap.
// Wires the static shell to the REST API + SSE event stream.
// All panel logic is delegated to ./panels/* modules.

console.log("[bAInary] app.js loading (v20260708)");

// Import each panel's namespace as an object so `panel.init(bus)` works
// even though the modules export named functions (init, refresh, ...).
import * as functionTree from "./panels/functionTree.js";
import * as asmPanel from "./panels/asm.js";
import * as codePanel from "./panels/code.js";
import * as graphPanel from "./panels/graph.js";
import * as ragPanel from "./panels/rag.js";
import * as stringsPanel from "./panels/strings.js";
import * as consolePanel from "./panels/console.js";
import * as hexPanel from "./panels/hex.js";
import { settingsPanel, openBinaryPanel } from "./panels/dialogs.js";

const bus = new EventTarget();

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

// Bridge the few window-scoped CustomEvents that the inline script in
// index.html publishes (it runs independently of app.js to guarantee the
// dialog works even if module loading fails).
function bridgeWindowEvents() {
  window.addEventListener("__bainary-log", (e) => {
    bus.dispatchEvent(new CustomEvent("log", { detail: e.detail }));
  });
  window.addEventListener("__bainary-lift-done", (e) => {
    bus.dispatchEvent(new CustomEvent("lift.done", { detail: e.detail || {} }));
  });
  window.addEventListener("__bainary-function-selected", (e) => {
    bus.dispatchEvent(new CustomEvent("function:selected", { detail: e.detail }));
  });
  window.addEventListener("__bainary-refresh", () => {
    functionTree.refresh(bus);
    graphPanel.refresh(bus);
    stringsPanel.refresh(bus);
  });
}

// SSE wiring: subscribe to backend events; dispatch as DOM CustomEvents.
function startSSE() {
  const es = new EventSource("/api/events");
  const known = ["lift.progress", "lift.done", "lift.error",
                 "refine.progress", "refine.done", "rag_build.done", "log"];
  for (const t of known) {
    es.addEventListener(t, (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { data = { raw: e.data }; }
      bus.dispatchEvent(new CustomEvent(t, { detail: data }));
    });
  }
  es.onerror = () => {
    bus.dispatchEvent(new CustomEvent("log", { detail: { level: "warn", msg: "SSE desconectado" } }));
  };
}

// Topbar button wiring.
function initTopbar() {
  $("#open-binary").addEventListener("click", () => openBinaryPanel.show());
  $("#open-settings").addEventListener("click", () => settingsPanel.show());
  $("#toggle-hex").addEventListener("click", () => hexPanel.toggle());
}

// Bottom-panel tab switcher.
function initBottomTabs() {
  $$("#bottom-tabs .tab").forEach(tab => {
    tab.addEventListener("click", () => {
      $$("#bottom-tabs .tab").forEach(t => t.setAttribute("aria-selected", "false"));
      tab.setAttribute("aria-selected", "true");
      const name = tab.dataset.tab;
      $$(".bottom-panel .tab-body").forEach(body => {
        const match = body.dataset.tab === name;
        body.toggleAttribute("hidden", !match);
        if (match) body.dataset.active = "true";
        else delete body.dataset.active;
      });
    });
  });
}

// Workspace code-panel tab switcher (Original|Refinado|Diff).
function initCodeTabs() {
  const tabs = $$("#code-pane .tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.setAttribute("aria-selected", "false"));
      tab.setAttribute("aria-selected", "true");
      codePanel.setView(tab.dataset.tab);
    });
  });
}

// Cross-panel: when a function is selected, all panels load it.
function initBusRouting() {
  bus.addEventListener("function:selected", (e) => {
    const { address, name } = e.detail;
    asmPanel.load(bus, address);
    codePanel.load(bus, address, name);
    graphPanel.focus(bus, address);
    $("#refine-one").disabled = false;
  });
  bus.addEventListener("lift.done", (e) => {
    const summary = e.detail;
    $("#lift-status").textContent = "lift done";
    functionTree.refresh(bus);
    graphPanel.refresh(bus);
    stringsPanel.refresh(bus);
  });
  bus.addEventListener("lift.error", (e) => {
    $("#lift-status").textContent = "lift error";
    console.error("[bAInary] lift error:", e.detail);
  });
}

function initResize() {
  // Sidebar drag handle.
  const sidebar = $("#sidebar");
  const handle = document.createElement("div");
  handle.style.cssText = "position:absolute;top:0;right:-3px;width:6px;height:100%;cursor:col-resize;";
  sidebar.style.position = "relative";
  sidebar.appendChild(handle);
  handle.addEventListener("mousedown", (down) => {
    const startX = down.clientX, startW = sidebar.getBoundingClientRect().width;
    const onMove = (m) => {
      const w = Math.max(160, Math.min(500, startW + m.clientX - startX));
      document.documentElement.style.setProperty("--sidebar-w", w + "px");
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

// Module scripts are deferred by the browser — the DOM is already parsed
// when this code runs. No need to wait for DOMContentLoaded; just execute.

try {
  console.log("[bAInary] initializing panels...");
  // Skip dialog wiring — index.html inline script already handles it.
  initBottomTabs();
  initCodeTabs();
  initBusRouting();
  initResize();
  startSSE();
  bridgeWindowEvents();
  consolePanel.init(bus);
  functionTree.init(bus);
  graphPanel.init(bus);
  ragPanel.init(bus);
  stringsPanel.init(bus);
  hexPanel.init(bus);
  console.log("[bAInary] all panels initialized");

  // Initial status pull.
  fetch("/api/binary").then(r => r.ok ? r.json() : null).then(info => {
    if (info && info.functions_count !== undefined) {
      $("#lift-status").textContent = `${info.functions_count} fn`;
      functionTree.refresh(bus);
      graphPanel.refresh(bus);
      stringsPanel.refresh(bus);
    }
  }).catch(() => {});
} catch (e) {
  console.error("[bAInary] FATAL during init:", e);
  const st = document.getElementById("lift-status");
  if (st) st.textContent = `Error: ${e.message}`;
}
