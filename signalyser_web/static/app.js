// Signalyser web: submit a tool run, then stream its output over SSE.
let activeSource = null;
let activeJob = null;
let activeToolLabel = "";

function $(id) { return document.getElementById(id); }

function setState(state) {
  // state: "" | running | done | error
  const out = $("output");
  const col = $("output-col");
  if (out) out.className = "output" + (state ? " " + state : "");
  if (col) col.dataset.state = state || "idle";
}

function setTitle(text) {
  const title = $("run-title");
  if (title) title.textContent = text;
}

function showToast(msg) {
  const t = $("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove("show"), 1600);
}

// Auto-scroll only when the user is already near the bottom.
function appendLine(out, line) {
  const nearBottom = out.scrollHeight - out.scrollTop - out.clientHeight < 40;
  out.textContent += line + "\n";
  if (nearBottom) out.scrollTop = out.scrollHeight;
}

async function runTool(event) {
  event.preventDefault();
  const form = event.target;
  const out = $("output");
  const cancelBtn = $("cancel-btn");
  const copyBtn = $("copy-btn");

  // Tear down any previous stream.
  if (activeSource) { activeSource.close(); activeSource = null; }

  activeToolLabel = form.dataset.label || form.dataset.tool;
  out.classList.remove("empty");
  out.textContent = "";
  setState("running");
  setTitle(activeToolLabel + " — running…");
  if (copyBtn) copyBtn.hidden = true;

  let resp;
  try {
    resp = await fetch("/run", { method: "POST", body: new FormData(form) });
  } catch (e) {
    out.textContent = "Network error: " + e;
    setState("error");
    setTitle(activeToolLabel + " — error");
    return false;
  }

  const data = await resp.json();
  if (!data.ok) {
    out.textContent = "⚠  " + (data.error || "Could not start run.");
    setState("error");
    setTitle(activeToolLabel + " — could not start");
    return false;
  }

  activeJob = data.job_id;
  if (cancelBtn) cancelBtn.hidden = false;

  const src = new EventSource("/stream/" + data.job_id);
  activeSource = src;
  src.onmessage = (ev) => { appendLine(out, ev.data); };
  src.addEventListener("done", (ev) => {
    src.close();
    activeSource = null;
    activeJob = null;
    if (cancelBtn) cancelBtn.hidden = true;
    if (copyBtn) copyBtn.hidden = false;
    const rc = parseInt(ev.data, 10);
    if (rc === 0) {
      setState("done");
      setTitle(activeToolLabel + " — done");
    } else {
      setState("error");
      setTitle(activeToolLabel + " — exited " + rc);
    }
  });
  src.onerror = () => {
    // EventSource auto-retries; if the job is gone, surface it once.
    if (activeSource) {
      setState("error");
      setTitle(activeToolLabel + " — connection lost");
      if (cancelBtn) cancelBtn.hidden = true;
    }
  };
  return false;
}

async function cancelRun() {
  if (!activeJob) return;
  setTitle(activeToolLabel + " — stopping…");
  await fetch("/cancel/" + activeJob, { method: "POST" });
}

async function copyOutput() {
  const out = $("output");
  if (!out) return;
  try {
    await navigator.clipboard.writeText(out.textContent);
    showToast("Output copied");
  } catch (e) {
    showToast("Copy failed");
  }
}

// Ctrl/Cmd+Enter submits the focused tool card.
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const card = document.activeElement && document.activeElement.closest("form.tool-card");
    if (card) { e.preventDefault(); card.requestSubmit(); }
  }
});
