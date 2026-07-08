// Console panel — subscribe to log/lift/refine SSE events and render.

export function init(bus) {
  const pre = document.getElementById("console-log");
  const handlers = {
    log: (d) => _line(pre, d.level || "info", d.msg || JSON.stringify(d)),
    "lift.progress": (d) => _line(pre, "info", `lift ${d.stage ?? "?"}`),
    "lift.done": (d) => _line(pre, "ok", `lift done: ${d.functions_count ?? "?"} fn`),
    "lift.error": (d) => _line(pre, "err", `lift error: ${d.detail ?? JSON.stringify(d)}`),
    "refine.progress": (d) => _line(pre, "info", `refine ${d.address} ${d.status ?? ""}`),
    "refine.done": (d) => _line(pre, "ok", `refine done: ${d.count ?? "?"}`),
    "rag_build.done": (d) => _line(pre, "ok", `rag build: ${d.count} funciones`),
  };
  for (const [name, fn] of Object.entries(handlers)) {
    bus.addEventListener(name, (e) => fn(e.detail));
  }
}

function _line(pre, level, msg) {
  const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
  const line = document.createElement("div");
  line.className = `line ${level}`;
  const tsSpan = document.createElement("span");
  tsSpan.className = "ts";
  tsSpan.textContent = ts;
  const tagSpan = document.createElement("span");
  tagSpan.className = "tag";
  tagSpan.textContent = `[${level}]`;
  const text = document.createElement("span");
  text.textContent = msg;
  line.append(tsSpan, tagSpan, text);
  pre.appendChild(line);
  pre.scrollTop = pre.scrollHeight;
  // bound the buffer
  while (pre.children.length > 500) pre.removeChild(pre.firstChild);
}
