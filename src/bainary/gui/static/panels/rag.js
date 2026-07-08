// RAG panel — build index, search, display hits.

let _built = false;

export function init(bus) {
  const buildBtn = document.getElementById("rag-build");
  const searchBtn = document.getElementById("rag-search");
  const query = document.getElementById("rag-query");
  buildBtn.addEventListener("click", async () => {
    buildBtn.disabled = true;
    bus.dispatchEvent(new CustomEvent("log", { detail: { level: "info", msg: "RAG build…" } }));
    try {
      const r = await fetch("/api/rag/build", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      _built = true;
      searchBtn.disabled = false;
      bus.dispatchEvent(new CustomEvent("log", { detail: { level: "ok", msg: `RAG build: ${j.count} funciones indexadas` } }));
    } catch (e) {
      bus.dispatchEvent(new CustomEvent("log", { detail: { level: "err", msg: `RAG build error: ${e.message}` } }));
    } finally {
      buildBtn.disabled = false;
    }
  });
  query.addEventListener("keydown", (e) => { if (e.key === "Enter") searchBtn.click(); });
  searchBtn.addEventListener("click", async () => {
    const q = query.value.trim();
    if (!q) return;
    try {
      const r = await fetch("/api/rag/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: q, k: 10 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const hits = await r.json();
      _render(hits, bus);
    } catch (e) {
      bus.dispatchEvent(new CustomEvent("log", { detail: { level: "err", msg: `RAG search: ${e.message}` } }));
    }
  });
}

function _render(hits, bus) {
  const ul = document.getElementById("rag-results");
  ul.innerHTML = "";
  const maxScore = hits.reduce((m, h) => Math.max(m, h.score), 0) || 1;
  for (const h of hits) {
    const li = document.createElement("li");
    const bar = document.createElement("div");
    bar.className = "score-bar";
    const fill = document.createElement("div");
    fill.className = "fill";
    fill.style.width = `${Math.round((h.score / maxScore) * 100)}%`;
    bar.appendChild(fill);
    const info = document.createElement("div");
    info.className = "hit-info";
    const nameSpan = document.createElement("span");
    nameSpan.className = "hit-name";
    nameSpan.textContent = h.function.name;
    info.append(nameSpan, document.createTextNode(" "), document.createTextNode(h.function.address));
    li.append(bar, info);
    li.addEventListener("click", () => {
      bus.dispatchEvent(new CustomEvent("function:selected", { detail: h.function }));
    });
    ul.appendChild(li);
  }
}
