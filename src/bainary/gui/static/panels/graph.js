// Graph panel — vis-network with the full call graph + N-hop focus on click.

let _network = null;
let _container = null;
let _hops = 1;
let _currentAddr = null;

export function init(bus) {
  _container = document.getElementById("graph-body");
  const hopsInput = document.getElementById("hops");
  hopsInput.addEventListener("input", () => {
    _hops = parseInt(hopsInput.value, 10) || 1;
    if (_currentAddr) focus(bus, _currentAddr);
  });
}

export async function refresh(bus) {
  try {
    const r = await fetch("/api/graph");
    if (!r.ok) return;
    const g = await r.json();
    await _render(g);
  } catch (e) {
    console.error("graphPanel.refresh", e);
  }
}

export async function focus(bus, address) {
  _currentAddr = address;
  try {
    const r = await fetch(`/api/graph/focus/${encodeURIComponent(address)}?depth=${_hops}`);
    if (!r.ok) return;
    const g = await r.json();
    await _render(g, address);
  } catch (e) {
    console.error("graphPanel.focus", e);
  }
}

async function _render(graph, highlightAddr) {
  const vis = await import("vis-network");
  const { DataSet } = await import("vis-data");
  const nodes = graph.nodes.map(n => ({
    id: n.id,
    label: n.name,
    color: highlightAddr && n.id === highlightAddr
      ? { background: "#4ec9b0", border: "#4ec9b0" }
      : (n.is_thunk ? { background: "#3a3a3a" } : (n.is_extern ? { background: "#5a4a2a" } : { background: "#2d2d30" })),
    font: { color: "#d4d4d4", size: 11 },
    shape: "box",
    margin: 4,
  }));
  const edges = graph.edges.map(([from, to]) => ({ from, to, arrows: "to", color: "#5a5a5a" }));
  const data = { nodes: new DataSet(nodes), edges: new DataSet(edges) };
  if (!_network) {
    _network = new vis.Network(_container, data, {
      layout: { hierarchical: { enabled: false } },
      physics: { enabled: true, stabilization: { iterations: 200 } },
      interaction: { hover: true, tooltipDelay: 200 },
    });
    _network.on("click", (params) => {
      if (params.nodes && params.nodes.length === 1) {
        const id = params.nodes[0];
        const node = nodes.find(n => n.id === id);
        if (node) {
          document.dispatchEvent(new CustomEvent("__graph-click", { detail: node }));
          // Re-dispatch as a normal selection so the rest of the UI reacts.
          window.dispatchEvent(new CustomEvent("__noop"));
        }
      }
    });
  } else {
    _network.setData(data);
  }
  // Bridge graph clicks to the bus: find by id.
  if (_network) {
    _network.off("selectNode");
    _network.on("selectNode", (params) => {
      const id = params.nodes[0];
      const node = graph.nodes.find(n => n.id === id);
      if (node) {
        bus.dispatchEvent(new CustomEvent("function:selected", { detail: node }));
      }
    });
  }
}
