const $ = (id) => document.getElementById(id);

async function loadBackends() {
  const res = await fetch("/api/backends");
  const data = await res.json();
  const select = $("backend");
  select.innerHTML = "";
  for (const name of data.backends) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  }
}

async function loadExample() {
  const res = await fetch("/api/examples/ticket_routing");
  if (!res.ok) {
    setStatus("example not found", true);
    return;
  }
  const tree = await res.json();
  $("tree").value = JSON.stringify(tree, null, 2);
  setStatus("example loaded", false);
}

function setStatus(msg, isError) {
  const el = $("tree-status");
  el.textContent = msg;
  el.classList.toggle("error", Boolean(isError));
}

function renderResult(payload) {
  const root = $("result");
  root.innerHTML = "";

  if (!payload.ok) {
    const title = document.createElement("p");
    title.className = "error";
    title.textContent = "Error: " + (payload.code || "unknown");
    root.appendChild(title);

    if (payload.message) {
      const pre = document.createElement("pre");
      pre.textContent = payload.message;
      root.appendChild(pre);
    }
    if (payload.errors) {
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(payload.errors, null, 2);
      root.appendChild(pre);
    }
    return;
  }

  const summary = document.createElement("p");
  summary.className = "result-summary";
  summary.textContent = "Result: " + payload.result + " (" + payload.steps + " steps)";
  root.appendChild(summary);

  const ol = document.createElement("ol");
  ol.className = "trace";
  for (const entry of payload.path) {
    const li = document.createElement("li");

    const head = document.createElement("div");
    head.className = "trace-head";
    head.textContent = entry.node_id + " -> " + entry.next_node +
      (entry.fell_back ? "  (fallback)" : "");
    li.appendChild(head);

    const q = document.createElement("div");
    q.className = "trace-q";
    q.textContent = entry.question;
    li.appendChild(q);

    const opts = document.createElement("div");
    opts.className = "trace-opts";
    for (const opt of entry.options) {
      const span = document.createElement("span");
      span.className = "opt" + (opt === entry.decision.label ? " chosen" : "");
      const score = entry.decision.scores ? entry.decision.scores[opt] : undefined;
      span.textContent = opt +
        (typeof score === "number" ? "  (" + score.toFixed(3) + ")" : "");
      opts.appendChild(span);
    }
    li.appendChild(opts);

    const meta = document.createElement("div");
    meta.className = "trace-meta";
    const lat = typeof entry.decision.latency_ms === "number"
      ? entry.decision.latency_ms.toFixed(2) + " ms"
      : "n/a";
    meta.textContent = "confidence " + entry.decision.confidence.toFixed(3) + " · " + lat;
    li.appendChild(meta);

    ol.appendChild(li);
  }
  root.appendChild(ol);
}

async function run() {
  const btn = $("run");
  btn.disabled = true;
  setStatus("", false);

  try {
    let tree;
    try {
      tree = JSON.parse($("tree").value);
    } catch (e) {
      renderResult({ ok: false, code: "invalid_json", message: String(e) });
      return;
    }

    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tree: tree,
        input: $("input").value,
        backend: $("backend").value,
        max_steps: Number($("max-steps").value) || 200,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      renderResult({
        ok: true,
        result: data.result,
        steps: data.steps,
        path: data.path,
      });
      return;
    }

    const body = await res.json().catch(() => ({}));
    const detail = body.detail || {};
    renderResult({
      ok: false,
      code: detail.code || "http_" + res.status,
      message: detail.message || body.message || "",
      errors: detail.errors,
    });
  } finally {
    btn.disabled = false;
  }
}

async function runFile() {
  const btn = $("run-file");
  const fileInput = $("file");
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    renderResult({ ok: false, code: "no_file", message: "Pick a file first." });
    return;
  }
  btn.disabled = true;
  try {
    let tree;
    try {
      tree = JSON.parse($("tree").value);
    } catch (e) {
      renderResult({ ok: false, code: "invalid_json", message: String(e) });
      return;
    }

    const fd = new FormData();
    fd.append("tree", JSON.stringify(tree));
    fd.append("backend", $("backend").value);
    fd.append("max_steps", String(Number($("max-steps").value) || 200));
    fd.append("file", file);

    const res = await fetch("/api/run-file", { method: "POST", body: fd });

    if (res.ok) {
      const data = await res.json();
      renderResult({
        ok: true,
        result: data.result,
        steps: data.steps,
        path: data.path,
      });
      return;
    }

    const body = await res.json().catch(() => ({}));
    const detail = body.detail || {};
    renderResult({
      ok: false,
      code: detail.code || "http_" + res.status,
      message: detail.message || body.message || "",
      errors: detail.errors,
    });
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadBackends();
  $("load-example").addEventListener("click", loadExample);
  $("run").addEventListener("click", run);
  $("run-file").addEventListener("click", runFile);
});
