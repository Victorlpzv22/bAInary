// Strings / Imports / Exports panel — three filterable tables.

const TABLES = { imports: "imports-table", exports: "exports-table", strings: "strings-table" };

export function init(bus) {
  for (const [kind, input] of document.querySelectorAll("[data-filter]").entries
    ? [[null, null]] // placeholder, replaced below
    : [[null, null]]) { /* noop */ }
  document.querySelectorAll("[data-filter]").forEach((el) => {
    el.addEventListener("input", () => {
      const kind = el.dataset.filter;
      _render(kind, el.value, bus);
    });
  });
}

export async function refresh(bus) {
  for (const kind of Object.keys(TABLES)) {
    try {
      const r = await fetch(`/api/${kind}`);
      if (!r.ok) continue;
      const rows = await r.json();
      window.__bainary_meta = window.__bainary_meta || {};
      window.__bainary_meta[kind] = rows;
      _render(kind, "", bus);
    } catch (e) {
      console.error(`stringsPanel.refresh ${kind}`, e);
    }
  }
}

function _render(kind, filter, bus) {
  const tbl = document.getElementById(TABLES[kind]);
  if (!tbl) return;
  tbl.innerHTML = "";
  const rows = (window.__bainary_meta?.[kind] || []).filter(r => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (r.name && r.name.toLowerCase().includes(q)) ||
           (r.value && r.value.toLowerCase().includes(q));
  });
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  for (const col of _columns(kind)) {
    const th = document.createElement("th");
    th.textContent = col;
    trh.appendChild(th);
  }
  thead.appendChild(trh);
  tbl.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const r of rows) {
    const tr = document.createElement("tr");
    for (const col of _columns(kind)) {
      const td = document.createElement("td");
      td.textContent = r[col] ?? "";
      tr.appendChild(td);
    }
    tr.addEventListener("click", () => {
      if (r.address) {
        bus.dispatchEvent(new CustomEvent("function:selected", { detail: { address: r.address, name: r.name } }));
      }
    });
    tbody.appendChild(tr);
  }
  tbl.appendChild(tbody);
}

function _columns(kind) {
  if (kind === "imports") return ["name", "library", "address"];
  if (kind === "exports") return ["name", "address"];
  return ["value", "address"];
}
