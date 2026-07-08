// bAInary GUI bootstrap.
// Wires the static shell to the REST API + SSE event stream.
// All panel logic is delegated to ./panels/* modules.

import { functionTree } from "./panels/functionTree.js";
import { asmPanel } from "./panels/asm.js";
import { codePanel } from "./panels/code.js";
import { graphPanel } from "./panels/graph.js";
import { ragPanel } from "./panels/rag.js";
import { stringsPanel } from "./panels/strings.js";
import { consolePanel } from "./panels/console.js";
import { hexPanel } from "./panels/hex.js";
import { settingsPanel, openBinaryPanel } from "./panels/dialogs.js";

const bus = new EventTarget();

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

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
  $("#open-binary").addEventListener("click", () => openBinaryPanel.show(bus));
  $("#open-settings").addEventListener("click", () => settingsPanel.show(bus));
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
  bus.addEventListener("lift:done", (e) => {
    const summary = e.detail;
    $("#lift-status").textContent = `${summary.functions_count} fn`;
    functionTree.refresh(bus);
    graphPanel.refresh(bus);
    stringsPanel.refresh(bus);
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

window.addEventListener("DOMContentLoaded", () => {
  initTopbar();
  initBottomTabs();
  initCodeTabs();
  initBusRouting();
  initResize();
  startSSE();
  consolePanel.init(bus);
  functionTree.init(bus);
  graphPanel.init(bus);
  ragPanel.init(bus);
  stringsPanel.init(bus);
  hexPanel.init(bus);
  // Initial status pull.
  fetch("/api/binary").then(r => r.ok ? r.json() : null).then(info => {
    if (info && info.functions_count !== undefined) {
      $("#lift-status").textContent = `${info.functions_count} fn`;
      functionTree.refresh(bus);
      graphPanel.refresh(bus);
      stringsPanel.refresh(bus);
    }
  }).catch(() => {});
});
