// Signalyser v2 dashboard — workflow runner with a sequential batch queue.
// Reuses the same /run + /stream (SSE) endpoints as v1. IIFE-scoped so nothing
// here collides with app.js (which is also loaded).
(function () {
  const el = (id) => document.getElementById(id);
  const consoleEl = () => el("v2-console");
  if (!consoleEl()) return;            // only the dashboard has the console

  const state = { source: null, job: null, busy: false };

  function setColState(s) { const c = el("v2-console-col"); if (c) c.dataset.state = s || "idle"; }
  function setStatus(t) { const s = el("v2-status"); if (s) s.textContent = t; }

  function write(text, cls) {
    const c = consoleEl();
    c.classList.remove("empty");
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = text + "\n";
    c.appendChild(span);
    c.scrollTop = c.scrollHeight;
  }
  const header = (t) => write("\n— " + t + " —", "ln-head");

  function setBusy(b) {
    state.busy = b;
    document.querySelectorAll(".deck-main button, .company-chip").forEach((btn) => { btn.disabled = b; });
    const cancel = el("v2-cancel"); if (cancel) cancel.hidden = !b;
  }

  function formData(tool, fields) {
    const f = new FormData();
    f.append("tool", tool);
    for (const k in fields) f.append(k, fields[k]);
    return f;
  }

  // POST /run then stream /stream/<job> until the 'done' event. Resolves the rc.
  function streamRun(fd) {
    return new Promise(async (resolve) => {
      let resp;
      try { resp = await fetch("/run", { method: "POST", body: fd }); }
      catch (e) { write("network error: " + e, "ln-err"); return resolve(null); }
      const data = await resp.json();
      if (!data.ok) { write("⚠  " + (data.error || "could not start run"), "ln-err"); return resolve(null); }
      state.job = data.job_id;
      const src = new EventSource("/stream/" + data.job_id);
      state.source = src;
      src.onmessage = (ev) => write(ev.data);
      src.addEventListener("done", (ev) => {
        src.close(); state.source = null; state.job = null;
        resolve(parseInt(ev.data, 10));
      });
      src.onerror = () => {
        if (state.source) { src.close(); state.source = null; write("connection lost", "ln-err"); resolve(null); }
      };
    });
  }

  async function runOne(tool, fields, label) {
    if (state.busy) return;
    setBusy(true); setColState("running"); setStatus(label + " — running…");
    header(label);
    const rc = await streamRun(formData(tool, fields));
    if (rc === 0) { setColState("done"); setStatus(label + " — done"); write("✓ done", "ln-ok"); }
    else { setColState("error"); setStatus(label + " — " + (rc == null ? "failed" : "exit " + rc)); }
    el("v2-copy").hidden = false;
    setBusy(false);
    return rc;
  }

  // Intake: split the textarea on commas / newlines and run the page decoder for
  // each URL, one after another, building the session corpus.
  async function runIntake() {
    if (state.busy) return;
    const raw = (el("intake-urls").value || "");
    const items = raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
    if (!items.length) { setStatus("enter at least one URL"); el("intake-urls").focus(); return; }

    setBusy(true); setColState("running");
    const prog = el("intake-progress");
    let ok = 0;
    for (let i = 0; i < items.length; i++) {
      setStatus("intake " + (i + 1) + "/" + items.length);
      if (prog) prog.textContent = (i + 1) + " / " + items.length;
      header("Intake " + (i + 1) + "/" + items.length + ": " + items[i]);
      const rc = await streamRun(formData("page", { url: items[i] }));
      if (rc === 0) ok++;
      write(rc === 0 ? "✓ added to corpus" : "✗ failed", rc === 0 ? "ln-ok" : "ln-err");
    }
    setColState(ok === items.length ? "done" : "error");
    setStatus("intake complete — " + ok + "/" + items.length + " added");
    if (prog) prog.innerHTML = ok + " / " + items.length + " added · <a href=\"/tools\">refresh corpus &#8635;</a>";
    el("v2-copy").hidden = false;
    setBusy(false);
  }

  function init() {
    el("intake-run").addEventListener("click", runIntake);

    document.querySelectorAll(".analyse-btn").forEach((b) => {
      b.addEventListener("click", () => {
        const company = (el("company").value || "").trim();
        if (!company) { setStatus("enter a company first"); el("company").focus(); return; }
        runOne(b.dataset.tool, { company }, b.textContent.trim() + " · " + company);
      });
    });

    const quad = el("quadrant-run");
    if (quad) quad.addEventListener("click", () => runOne("quadrant", {}, "Competitive Quadrant"));

    const opp = el("opp-run");
    if (opp) opp.addEventListener("click", () => {
      const company = (el("company").value || "").trim();
      const sub = (el("opp-sub").value || "").trim();
      if (!company) { setStatus("enter a company first"); el("company").focus(); return; }
      if (!sub) { setStatus("enter a subreddit to scan"); el("opp-sub").focus(); return; }
      runOne("opportunities", { company, subreddit: sub }, "Opportunity scan · " + company + " × r/" + sub);
    });

    document.querySelectorAll(".inst-run").forEach((b) => {
      b.addEventListener("click", () => {
        const map = (b.dataset.field || "").split(",").map((s) => s.split(":"));
        const fields = {};
        for (const [name, id] of map) {
          const v = ((el(id) || {}).value || "").trim();
          if (v) fields[name] = v;
        }
        const primary = map[0][0];
        if (!fields[primary]) { setStatus("fill in the " + primary + " first"); return; }
        runOne(b.dataset.tool, fields, b.textContent.trim());
      });
    });

    document.querySelectorAll(".company-chip").forEach((ch) => {
      ch.addEventListener("click", () => { el("company").value = ch.dataset.company; el("company").focus(); });
    });

    el("v2-cancel").addEventListener("click", async () => {
      if (state.job) { setStatus("stopping…"); await fetch("/cancel/" + state.job, { method: "POST" }); }
    });
    el("v2-clear").addEventListener("click", () => {
      const c = consoleEl();
      c.innerHTML = ""; c.textContent = "Idle."; c.classList.add("empty");
      setColState("idle"); setStatus("Console"); el("v2-copy").hidden = true;
    });
    el("v2-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(consoleEl().innerText); setStatus("output copied"); } catch (e) {}
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
