/* ClaimGuard AI web UI. Works against the FastAPI backend, or in "showcase" mode
   from data embedded in window.__STATIC__ (see scripts/build_showcase.py). */
(() => {
  "use strict";
  const S = window.__STATIC__ || null;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ANALYSTS = ["policy", "medical", "billing", "provider", "history"];

  const inr = (n) => {
    if (n === null || n === undefined || n === "") return "–";
    const neg = n < 0; let s = String(Math.round(Math.abs(n)));
    if (s.length > 3) { let head = s.slice(0, -3); const tail = s.slice(-3); const parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head); s = parts.join(",") + "," + tail; }
    return (neg ? "−" : "") + "₹" + s;
  };
  const STATUS_TEXT = { AUTO_APPROVE: "Auto-approved", HUMAN_REVIEW: "Human review", SIU_INVESTIGATION: "SIU investigation",
    NOT_ADMISSIBLE: "Not admissible", PENDING_DOCUMENTS: "Documents pending" };

  // ------------------------------------------------------------------ data layer
  const api = {
    async get(path) { const r = await fetch(path); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json(); },
    samples() { return S ? Promise.resolve(S.samples) : this.get("/api/samples"); },
    runSample(id) {
      if (S) return new Promise((res) => setTimeout(() => res(S.results[id]), reduced ? 0 : 450));
      return fetch(`/api/samples/${encodeURIComponent(id)}/run`, { method: "POST" }).then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Run failed"); return r.json(); });
    },
    upload(fd) {
      return fetch("/api/claims/upload", { method: "POST", body: fd }).then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Upload failed"); return r.json(); });
    },
    claims() { return S ? Promise.resolve({ runs: S.runs, stats: {} }) : this.get("/api/claims"); },
    workflow() { return S ? Promise.resolve(S.workflow) : this.get("/api/workflow"); },
    model() { return S ? Promise.resolve(S.model) : this.get("/api/model"); },
    fileUrl(id, f) { return S ? (S.pdfs[`${id}/${f}`] || "#") : `/api/samples/${encodeURIComponent(id)}/files/${encodeURIComponent(f)}`; },
    reportUrl(r) {
      if (!S) return `/api/claims/${encodeURIComponent(r.run_id)}/report`;
      const html = S.reports[r.claim_id]; return html ? URL.createObjectURL(new Blob([html], { type: "text/html" })) : "#";
    },
  };

  // ------------------------------------------------------------------ router
  const views = ["assess", "register", "how", "model"];
  function show(view) {
    if (!views.includes(view)) view = "assess";
    views.forEach((v) => { $(`view-${v}`).hidden = v !== view; });
    document.querySelectorAll(".tabs a").forEach((a) => { if (a.dataset.view !== view) a.removeAttribute("aria-current"); else a.setAttribute("aria-current", "page"); });
    if (view === "register") loadRegister();
    if (view === "how") loadHow();
    if (view === "model") loadModel();
  }
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));

  // ------------------------------------------------------------------ assess
  let samples = [], current = null, lastResult = null;
  const expectBand = (t) => ((/\b(LOW|MEDIUM|HIGH)\b/.exec(t) || [])[1]) || "NA";
  const expectWord = { HIGH: "High risk", MEDIUM: "Review", LOW: "Genuine", NA: "Incomplete" };

  async function loadSamples() {
    samples = await api.samples();
    $("sample-list").innerHTML = samples.map((s) => {
      const b = expectBand(s.expected);
      return `<li><button type="button" data-id="${esc(s.claim_id)}" aria-pressed="false">
        <span class="s-id"><span>${esc(s.claim_id)}</span><span class="s-badge b-${b}">${expectWord[b]}</span></span>
        <span class="s-title">${esc(s.title)}</span></button></li>`;
    }).join("");
    $("sample-list").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => select(b.dataset.id)));
  }

  const pdfIcon = '<svg viewBox="0 0 14 16" aria-hidden="true"><path d="M1 1h8l4 4v10H1z" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M9 1v4h4" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';
  const docName = (f) => f.replace(/\.pdf$/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

  function select(id) {
    current = samples.find((s) => s.claim_id === id);
    $("sample-list").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
    $("empty-state").hidden = true; $("selected").hidden = false; $("result").hidden = true; $("error").hidden = true;
    $("sel-id").textContent = `${current.claim_id}, ${current.patient}, claimed ${current.claimed_amount.replace("Rs. ", "₹").replace(".00", "")}`;
    $("sel-title").textContent = current.title;
    $("sel-expected").textContent = `What the documents are designed to show: ${current.expected}.`;
    $("sel-docs").innerHTML = current.files.map((f) => { const u = api.fileUrl(current.claim_id, f);
      return u === "#" ? `<span class="doc-chip">${pdfIcon}${esc(docName(f))}</span>` : `<a class="doc-chip" href="${u}" target="_blank" rel="noopener">${pdfIcon}${esc(docName(f))}</a>`; }).join("");
    $("run-btn").focus({ preventScroll: true });
  }

  async function run(promise) {
    $("running").hidden = false; $("result").hidden = true; $("error").hidden = true;
    $("run-btn").disabled = true; $("upload-btn").disabled = true;
    try { const r = await promise; render(r); }
    catch (e) { $("error").textContent = `The agents could not finish: ${e.message}`; $("error").hidden = false; }
    finally { $("running").hidden = true; $("run-btn").disabled = false; $("upload-btn").disabled = !$("upload-input").files.length || !!S; }
  }
  $("run-btn").addEventListener("click", () => current && run(api.runSample(current.claim_id)));

  // upload
  const input = $("upload-input"), drop = $("drop");
  function syncNames() { $("upload-names").textContent = [...input.files].map((f) => f.name).join(", "); $("upload-btn").disabled = !input.files.length || !!S; }
  input.addEventListener("change", syncNames);
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; syncNames(); } });
  $("upload-form").addEventListener("submit", (e) => {
    e.preventDefault(); if (S || !input.files.length) return;
    const fd = new FormData(); [...input.files].forEach((f) => fd.append("files", f));
    current = null; $("sample-list").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    $("empty-state").hidden = true; $("selected").hidden = false;
    $("sel-id").textContent = "Uploaded documents"; $("sel-title").textContent = [...input.files].map((f) => f.name).join(", ");
    $("sel-expected").textContent = ""; $("sel-docs").innerHTML = "";
    run(api.upload(fd));
  });

  // ------------------------------------------------------------------ render result
  function render(r) {
    lastResult = r;
    const c = r.claim_summary || {};
    const band = r.risk_band || "NA";
    const facts = [
      ["Patient", `${c.patient_name ?? "–"}${c.patient_age ? `, ${c.patient_age}` : ""}`],
      ["Policy", `${c.policy_number ?? "–"}`], ["Plan", c.plan ?? "–"],
      ["Hospital", c.hospital_name ?? "–"],
      ["Provider type", c.hospital_tier ? `${c.hospital_tier.replace("_", " ")}, ${c.network ? "network" : "non-network"}` : (r.status === "PENDING_DOCUMENTS" ? "checked once documents arrive" : "not in registry")],
      ["Diagnosis", `${c.diagnosis ?? "–"}${c.icd10 ? ` (${c.icd10})` : ""}`],
      ["Stay", c.admission_date ? `${c.admission_date} to ${c.discharge_date} (${c.los_days} d)` : "–"],
      ["Claimed", `${inr(c.claimed_amount)} ${c.claim_type ? `(${c.claim_type})` : ""}`],
      ["Bill number", c.bill_no ?? "–"],
    ];
    $("facts").innerHTML = facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");

    const stamp = $("stamp");
    stamp.className = `stamp ${band}`; stamp.textContent = STATUS_TEXT[r.status] || r.status;
    $("score-num").textContent = r.fraud_score === null ? "—" : Math.round(r.fraud_score);
    $("needle").style.left = "0%";
    const d = r.decision;
    $("score-split").textContent = d ? `${r.risk_label}. Rules ${d.rule_score} × ${d.weights.rules} + ML ${d.ml_score} × ${d.weights.ml}${d.critical_override ? ", raised by a critical finding" : ""}.` : "Not scored until the missing documents arrive.";
    $("recommendation").textContent = r.recommendation;

    // categories + findings
    const cats = r.triggered_categories || [];
    const color = (s) => s >= 40 ? "var(--high)" : s >= 20 ? "var(--med)" : "var(--ink-soft)";
    $("categories").innerHTML = cats.length ? cats.map((x) => `<div class="cat-row"><span>${esc(x.label)}</span>
      <span class="cat-bar"><i style="width:${x.score}%;background:${color(x.score)}"></i></span><span class="cat-score">${Math.round(x.score)}</span></div>`).join("")
      : `<p class="none">${r.status === "PENDING_DOCUMENTS" ? "Scoring waits for the missing documents." : "No fraud category was triggered."}</p>`;
    const fs = r.findings || [];
    $("findings").innerHTML = fs.map((f) => `<li><span class="sev sev-${f.severity}">${f.severity.toLowerCase()}</span>
      <div>${esc(f.reason)}<div class="f-meta">${esc(f.category_label)}, raised by ${esc(f.agent)}</div></div></li>`).join("");

    renderTimeline(r);
    renderOutcome(r);

    $("output-text").textContent = r.output_text;
    $("narrative").textContent = r.narrative;
    $("report-link").href = api.reportUrl(r);

    // checks, ML, items
    const checks = (r.validation && r.validation.checks) || [];
    $("checks").innerHTML = checks.map((k) => `<li><span class="${k.passed ? "ok" : "bad"}" aria-label="${k.passed ? "passed" : "failed"}">${k.passed ? "✓" : "✗"}</span>
      <span>${esc(k.check)}<small>${esc(k.detail)}</small></span></li>`).join("");
    const ml = r.ml;
    $("ml").innerHTML = ml ? `<dl class="kv"><dt>Fraud probability</dt><dd>${(ml.fraud_probability * 100).toFixed(1)}%</dd>
      <dt>Anomaly vs genuine claims</dt><dd>${ml.anomaly_score} / 100</dd><dt>Model</dt><dd>${esc(ml.model_version)}, ROC-AUC ${ml.model_metrics.roc_auc}</dd></dl>
      <p class="note">Strongest drivers for this claim</p><div class="drivers">${(ml.top_drivers.length ? ml.top_drivers : [{ label: "Nothing unusual", weight: 0 }]).map((x) =>
        `<div class="driver"><span>${esc(x.label)}${x.value !== undefined ? ` <span class="note">(${x.value})</span>` : ""}</span><span class="cat-bar"><i style="width:${Math.min(100, x.weight * 80)}%;background:var(--stamp)"></i></span></div>`).join("")}</div>`
      : `<p class="none">The model runs once the claim file is complete.</p>`;
    const flagged = new Set(fs.flatMap((f) => (f.evidence && f.evidence.items) ? f.evidence.items.map((i) => typeof i === "string" ? i : i.item) : []));
    const items = r.line_items || [];
    $("items").innerHTML = `<thead><tr><th>#</th><th>Particulars</th><th>Category</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead><tbody>` +
      items.map((i) => `<tr class="${flagged.has(i.description) ? "flag" : ""}"><td>${i.sno}</td><td>${esc(i.description)}</td><td>${i.category}</td><td class="num">${i.qty}</td><td class="num">${inr(i.rate)}</td><td class="num">${inr(i.amount)}</td></tr>`).join("") +
      `</tbody><tfoot><tr><th colspan="5">Items total (bill grand total ${inr(c.billed_total)})</th><th class="num">${inr(items.reduce((a, i) => a + i.amount, 0))}</th></tr></tfoot>`;

    $("result").hidden = false;
    $("result").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    animate(r);
  }

  function renderTimeline(r) {
    const tr = r.agent_trace || [];
    $("engine-note").textContent = `${tr.length} agents on the ${r.engine === "langgraph" ? "LangGraph" : "built-in"} engine, ${Math.round(tr.reduce((a, t) => a + t.duration_ms, 0))} ms of agent time.`;
    const out = []; let par = [];
    const flush = () => { if (par.length) { out.push(`<li class="t-step"><span class="t-dot"></span><div class="t-name">Analyst agents, in parallel<span class="t-ms">${Math.round(Math.max(...par.map((p) => p.duration_ms)))} ms</span></div>
      <div class="t-par">${par.map((p) => `<div><b>${esc(p.agent.replace(" Agent", ""))}</b>${esc(p.summary)}</div>`).join("")}</div></li>`); par = []; } };
    tr.forEach((t) => {
      if (ANALYSTS.includes(t.node)) { par.push(t); return; }
      flush();
      out.push(`<li class="t-step ${t.status === "failed" ? "failed" : ""}"><span class="t-dot"></span><div class="t-name">${esc(t.agent)}<span class="t-ms">${t.duration_ms.toFixed(0)} ms</span></div><div class="t-sum">${esc(t.summary)}</div></li>`);
    });
    flush();
    $("timeline").innerHTML = out.join("");
  }

  function renderOutcome(r) {
    let h = "";
    if (r.status === "PENDING_DOCUMENTS") {
      $("outcome-title").textContent = "Documents requested";
      h = `<p>The claim is paused. This letter goes to the policyholder:</p><pre class="letter">${esc(r.doc_request.letter)}</pre>`;
    } else if (r.siu) {
      const s = r.siu; $("outcome-title").textContent = `SIU case ${s.case_id}`;
      h = `<dl class="kv"><dt>Priority</dt><dd>${esc(s.priority)}</dd><dt>Due by</dt><dd>${esc(s.due_by)}</dd><dt>Payment on hold</dt><dd>${inr(s.exposure)}</dd></dl>
        <p class="note">Investigation plan</p><ol class="tasks">${s.tasks.map((t) => `<li>${esc(t.task)}</li>`).join("")}</ol>`;
    } else if (r.settlement) {
      const s = r.settlement; $("outcome-title").textContent = "Settlement";
      h = `<table class="lines">${s.lines.map((l, i) => `<tr class="${i === s.lines.length - 1 ? "total" : ""}"><td>${esc(l.label)}</td><td>${inr(l.amount)}</td></tr>`).join("")}</table>
        <p class="note">${esc(s.status)}. ${esc((s.notes || []).join(" "))}</p>`;
      const cov = r.decision && r.decision.coverage;
      if (cov && cov.issues && cov.issues.length) h += `<p class="note"><b>Coverage issues:</b> ${esc(cov.issues.join("; "))}</p>`;
    }
    $("outcome").innerHTML = h;
  }

  function animate(r) {
    const steps = [...document.querySelectorAll("#timeline .t-step")];
    const stamp = $("stamp");
    const finish = () => { $("needle").style.left = `${r.fraud_score ?? 0}%`; stamp.classList.remove("land"); void stamp.offsetWidth; stamp.classList.add("land"); };
    if (reduced) { steps.forEach((s) => s.classList.add("on")); $("needle").style.left = `${r.fraud_score ?? 0}%`; return; }
    stamp.style.visibility = "hidden";
    steps.forEach((s, i) => setTimeout(() => s.classList.add("on"), 90 * i));
    setTimeout(() => { stamp.style.visibility = "visible"; finish(); }, 90 * steps.length + 80);
  }

  $("copy-btn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("output-text").textContent); $("copy-btn").textContent = "Copied"; }
    catch { $("copy-btn").textContent = "Copy failed"; }
    setTimeout(() => { $("copy-btn").textContent = "Copy output"; }, 1600);
  });
  $("json-btn").addEventListener("click", () => {
    if (!lastResult) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" }));
    a.download = `${lastResult.claim_id}_${lastResult.run_id}.json`; a.click();
  });

  // ------------------------------------------------------------------ register
  async function loadRegister() {
    const { runs } = await api.claims();
    const counts = {}; runs.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
    $("reg-stats").innerHTML = [`<div class="stat"><b>${runs.length}</b><span>claims processed</span></div>`]
      .concat(Object.entries(counts).map(([k, v]) => `<div class="stat"><b>${v}</b><span>${STATUS_TEXT[k] || k}</span></div>`)).join("");
    $("register").innerHTML = `<thead><tr><th>Claim</th><th>Processed</th><th>Patient</th><th>Hospital</th><th>Diagnosis</th><th class="num">Claimed</th><th class="num">Score</th><th>Decision</th><th class="num">Payable</th></tr></thead><tbody>` +
      (runs.length ? runs.map((r) => `<tr><td>${S ? esc(r.claim_id) : `<a href="/api/claims/${encodeURIComponent(r.run_id)}/report" target="_blank" rel="noopener">${esc(r.claim_id)}</a>`}</td>
        <td>${esc((r.processed_at || "").replace("T", " "))}</td><td>${esc(r.patient)}</td><td>${esc(r.hospital)}</td><td>${esc(r.diagnosis)}</td>
        <td class="num">${inr(r.claimed_amount)}</td><td class="num">${r.fraud_score ?? "–"}</td>
        <td><span class="s-badge b-${r.risk_band || "NA"}">${STATUS_TEXT[r.status] || r.status}</span></td><td class="num">${r.payable == null ? "–" : inr(r.payable)}</td></tr>`).join("")
        : `<tr><td colspan="9" class="none">No claims yet. Run one from “Assess a claim”.</td></tr>`) + "</tbody>";
  }

  // ------------------------------------------------------------------ how it works
  let howLoaded = false;
  async function loadHow() {
    if (howLoaded) return; howLoaded = true;
    const w = await api.workflow();
    $("agents-table").innerHTML = `<thead><tr><th>Node</th><th>Agent</th><th>What it does</th></tr></thead><tbody>` +
      w.agents.map((a) => `<tr><td><code>${esc(a.node)}</code></td><td>${esc(a.name)}</td><td>${esc(a.role)}</td></tr>`).join("") + "</tbody>";
    const sc = w.scoring;
    $("formula").innerHTML = `Fraud score = ${sc.rule_weight} × rule score + ${sc.ml_weight} × ML score. The rule score combines categories with a noisy-OR, and findings inside one category count with diminishing weight. Any critical finding (tampered document, duplicate bill, blacklisted hospital, unknown policy) lifts the score to at least 70. Below ${sc.low_max} is genuine, ${sc.low_max} to ${sc.medium_max} goes to a human reviewer, above ${sc.medium_max} goes to the Special Investigation Unit.`;
    $("cat-list").innerHTML = Object.values(w.categories).map((c) => `<li>${esc(c)}</li>`).join("");
    const name = Object.fromEntries(w.agents.map((a) => [a.node, a.name.replace(" Agent", "")]));
    const box = (n, cls = "") => `<div class="fl-box ${cls}"><b>${esc(name[n] || n)}</b><code>${esc(n)}</code></div>`;
    const arrow = (label = "") => `<div class="fl-arrow">${label ? `<span>${esc(label)}</span>` : ""}</div>`;
    $("diagram").innerHTML = `<div class="flow">
      ${box("intake")}${arrow()}${box("classify")}${arrow()}${box("extract")}${arrow()}${box("validate")}
      <div class="fl-split"><div class="fl-branch">${arrow("documents complete")}${box("knowledge")}${arrow("fan-out")}
        <div class="fl-par">${ANALYSTS.map((a) => box(a, "par")).join("")}</div>${arrow("join: waits for all five")}${box("ml_scoring")}${arrow()}${box("decision")}
        <div class="fl-split"><div class="fl-branch">${arrow("low / medium risk")}${box("settlement")}</div><div class="fl-branch">${arrow("high risk")}${box("siu", "alert")}</div></div></div>
        <div class="fl-branch side">${arrow("documents missing")}${box("request_docs", "alert")}</div></div>
      ${arrow()}${box("report", "end")}</div>
      <details class="fl-src"><summary>Mermaid source of the graph</summary><pre>${esc(w.mermaid)}</pre></details>`;
  }

  // ------------------------------------------------------------------ model
  let modelLoaded = false;
  async function loadModel() {
    if (modelLoaded) return; modelLoaded = true;
    const m = await api.model();
    const stat = (v, l) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`;
    $("model-metrics").innerHTML = stat(m.roc_auc, "ROC-AUC on held-out claims") + stat(m.pr_auc, "PR-AUC") + stat(m["precision@0.5"], "Precision at 0.5")
      + stat(m["recall@0.5"], "Recall at 0.5") + stat(m.rows.toLocaleString("en-IN"), "training claims") + stat(`${(m.fraud_rate * 100).toFixed(1)}%`, "labelled fraud rate");
    const imp = Object.entries(m.feature_importance); const max = Math.max(...imp.map(([, v]) => v));
    $("importance").innerHTML = imp.map(([k, v]) => `<div class="imp-row"><span>${esc(k.replace(/_/g, " "))}</span><span class="cat-bar"><i style="width:${(v / max) * 100}%"></i></span><span class="cat-score">${(v * 100).toFixed(1)}%</span></div>`).join("");
  }

  // ------------------------------------------------------------------ boot
  if (S) { $("static-banner").hidden = false; $("upload-btn").disabled = true; input.disabled = true; }
  loadSamples().then(() => show(location.hash.slice(1) || "assess")).catch((e) => {
    $("error").textContent = `Could not load sample claims: ${e.message}`; $("error").hidden = false; });
})();
