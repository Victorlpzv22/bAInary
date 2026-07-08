// Dialogs: open-binary and settings.

const $ = (s) => document.querySelector(s);

export const openBinaryPanel = {
  show(bus) {
    const dlg = $("#dialog-open");
    dlg.showModal();
    $("[name=src]").forEach(r => r.addEventListener("change", () => {
      const useUpload = $("[name=src]:checked").value === "upload";
      $("#open-file").disabled = !useUpload;
      $("#open-path").disabled = useUpload;
    }));
    $("#open-submit").onclick = async () => {
      const src = $("[name=src]:checked").value;
      const backend = $("#open-backend").value;
      const err = $("#open-error");
      err.hidden = true;
      try {
        const r = src === "upload"
          ? await _upload(bus, backend)
          : await _path(bus, backend);
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          err.textContent = j.detail || `HTTP ${r.status}`;
          err.hidden = false;
          return;
        }
        const j = await r.json();
        bus.dispatchEvent(new CustomEvent("log", { detail: { level: "info", msg: `lift job ${j.job_id}` } }));
        dlg.close();
      } catch (e) {
        err.textContent = e.message;
        err.hidden = false;
      }
    };
  },
};

async function _upload(bus, backend) {
  const f = $("#open-file").files[0];
  if (!f) throw new Error("selecciona un fichero");
  const fd = new FormData();
  fd.append("file", f);
  return fetch(`/api/lift/upload?backend=${encodeURIComponent(backend)}`, { method: "POST", body: fd });
}

async function _path(bus, backend) {
  const p = $("#open-path").value.trim();
  if (!p) throw new Error("introduce una ruta");
  return fetch("/api/lift/path", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ path: p, backend }),
  });
}

export const settingsPanel = {
  async show(bus) {
    const dlg = $("#dialog-settings");
    const err = $("#settings-error");
    err.hidden = true;
    try {
      const r = await fetch("/api/settings");
      const s = await r.json();
      $("#set-provider").value = s.llm_provider || "";
      $("#set-model").value = s.llm_model || "";
      $("#set-url").value = s.llm_base_url || "";
      $("#set-lift").value = s.lift_backend || "";
      $("#set-key").value = "";
      $("#set-key").placeholder = s.api_key_masked || "(sin clave)";
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    }
    dlg.showModal();
    $("#settings-save").onclick = async () => {
      err.hidden = true;
      const body = {
        LLM_PROVIDER: $("#set-provider").value,
        LLM_MODEL: $("#set-model").value,
        LLM_BASE_URL: $("#set-url").value,
        LIFT_BACKEND: $("#set-lift").value,
      };
      const key = $("#set-key").value;
      if (key) body.OPENCODE_APIKEY = key;
      try {
        const r = await fetch("/api/settings", {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          err.textContent = j.detail || `HTTP ${r.status}`;
          err.hidden = false;
          return;
        }
        dlg.close();
      } catch (e) {
        err.textContent = e.message;
        err.hidden = false;
      }
    };
  },
};
