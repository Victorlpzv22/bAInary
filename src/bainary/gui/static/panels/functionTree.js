// Function-tree sidebar: filter, click-to-select, drag for RAG similar.

let _all = [];
let _filter = "";

export async function init(bus) {
  const input = document.getElementById("function-filter");
  input.addEventListener("input", () => {
    _filter = input.value.toLowerCase();
    render(bus);
  });
}

export async function refresh(bus) {
  try {
    const r = await fetch("/api/functions");
    if (!r.ok) return;
    _all = await r.json();
    render(bus);
  } catch (e) {
    console.error("functionTree.refresh", e);
  }
}

function render(bus) {
  const ul = document.getElementById("function-list");
  ul.innerHTML = "";
  const items = _all.filter(f => !_filter || f.name.toLowerCase().includes(_filter));
  for (const fn of items.slice(0, 1000)) {
    const li = document.createElement("li");
    li.className = fn.is_thunk ? "thunk" : (fn.is_extern ? "extern" : "");
    const nameSpan = document.createElement("span");
    nameSpan.className = "name";
    nameSpan.textContent = fn.name;
    const addrSpan = document.createElement("span");
    addrSpan.className = "addr";
    addrSpan.textContent = fn.address;
    li.append(nameSpan, addrSpan);
    li.title = `${fn.name} @ ${fn.address} (${fn.size_bytes} bytes)`;
    li.addEventListener("click", () => {
      document.querySelectorAll(".function-list li.active").forEach(el => el.classList.remove("active"));
      li.classList.add("active");
      bus.dispatchEvent(new CustomEvent("function:selected", { detail: fn }));
    });
    li.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/x-bainary-addr", fn.address);
      e.dataTransfer.effectAllowed = "copy";
    });
    ul.appendChild(li);
  }
  if (items.length > 1000) {
    const more = document.createElement("li");
    more.className = "thunk";
    more.textContent = `… (${items.length - 1000} más, refina el filtro)`;
    ul.appendChild(more);
  }
}
