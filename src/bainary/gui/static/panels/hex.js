// Hex overlay — paginated 16-byte rows, address jump, click-byte-to-ASM.

let _visible = false;

export function init(bus) {
  document.getElementById("hex-close").addEventListener("click", () => toggle(false));
  document.getElementById("hex-goto").addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      const v = e.target.value.trim();
      if (/^0x[0-9a-fA-F]+$/.test(v)) await _render(v);
    }
  });
}

export function toggle(force) {
  const overlay = document.getElementById("hex-overlay");
  _visible = force === undefined ? !_visible : force;
  overlay.toggleAttribute("hidden", !_visible);
  if (_visible) _render(document.getElementById("hex-goto").value || "0x0");
}

async function _render(addr) {
  const body = document.getElementById("hex-body");
  body.textContent = "cargando…";
  try {
    const r = await fetch(`/api/hex?addr=${encodeURIComponent(addr)}&len=512`);
    if (!r.ok) {
      body.textContent = `error: HTTP ${r.status}`;
      return;
    }
    const j = await r.json();
    body.innerHTML = "";
    for (const row of j.rows) {
      const div = document.createElement("div");
      div.className = "hex-row";
      const off = document.createElement("span");
      off.className = "off";
      off.textContent = row.off;
      const hex = document.createElement("span");
      hex.className = "hex";
      hex.textContent = row.hex;
      const ascii = document.createElement("span");
      ascii.className = "ascii";
      ascii.textContent = row.ascii;
      div.append(off, hex, ascii);
      body.appendChild(div);
    }
  } catch (e) {
    body.textContent = `error: ${e.message}`;
  }
}
