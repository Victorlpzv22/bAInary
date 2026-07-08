// Dialogs: open-binary and settings.

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let _openWired = false;
let _settingsWired = false;

function _wireOpenOnce() {
  if (_openWired) return;
  _openWired = true;

  // Toggle file-vs-path inputs when the radio changes.
  $$("[name=src]").forEach((r) => {
    r.addEventListener("change", () => {
      const useUpload = $("[name=src]:checked").value === "upload";
      $("#open-file").disabled = !useUpload;
      $("#open-path").disabled = useUpload;
      if (useUpload) $("#open-path").value = "";
      else $("#open-file").value = "";
    });
  });

  $("#open-submit").addEventListener("click", async (ev) => {
    ev.preventDefault();
    const err = $("#open-error");
    err.hidden = true;
    const src = $("[name=src]:checked").value;
    const backend = $("#open-backend").value;
    try {
      const r = src === "upload"
        ? await _upload(backend)
        : await _path(backend);
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        err.textContent = typeof j.detail === "string"
          ? j.detail
          : `HTTP ${r.status}`;
        err.hidden = false;
        return;
      }
      const j = await r.json();
      window.dispatchEvent(new CustomEvent("__bainary-log", {
        detail: { level: "info", msg: `lift job ${j.job_id}` },
      }));
      $("#dialog-open").close();
    } catch (e) {
      err.textContent = e?.message ?? String(e);
      err.hidden = false;
    }
  });
}

async function _upload(backend) {
  const f = $("#open-file").files[0];
  if (!f) throw new Error("selecciona un fichero");
  const fd = new FormData();
  fd.append("file", f);
  return fetch(`/api/lift/upload?backend=${encodeURIComponent(backend)}`, {
    method: "POST",
    body: fd,
  });
}

async function _path(backend) {
  const p = $("#open-path").value.trim();
  if (!p) throw new Error("introduce una ruta");
  return fetch("/api/lift/path", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ path: p, backend }),
  });
}

function _wireSettingsOnce() {
  if (_settingsWired) return;
  _settingsWired = true;

  $("#settings-save").addEventListener("click", async (ev) => {
    ev.preventDefault();
    const err = $("#settings-error");
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
        err.textContent = typeof j.detail === "string"
          ? j.detail
          : `HTTP ${r.status}`;
        err.hidden = false;
        return;
      }
      $("#dialog-settings").close();
    } catch (e) {
      err.textContent = e?.message ?? String(e);
      err.hidden = false;
    }
  });
}

export const openBinaryPanel = {
  show() {
    _wireOpenOnce();
    // Reset state every time the dialog opens.
    const err = $("#open-error");
    err.hidden = true;
    err.textContent = "";
    $("#open-file").value = "";
    $("#open-path").value = "";
    const checked = $("[name=src]:checked");
    if (checked) {
      const useUpload = checked.value === "upload";
      $("#open-file").disabled = !useUpload;
      $("#open-path").disabled = useUpload;
    }
    $("#dialog-open").showModal();
  },
};

export const settingsPanel = {
  async show() {
    _wireSettingsOnce();
    const err = $("#settings-error");
    err.hidden = true;
    err.textContent = "";
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
      err.textContent = e?.message ?? String(e);
      err.hidden = false;
    }
    $("#dialog-settings").showModal();
  },
};
