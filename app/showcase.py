"""Run every sample claim once and write the showcase outputs (inputs ready -> outputs ready).

outputs/
  <CLAIM-ID>/result.json      full decision record
  <CLAIM-ID>/report.html      printable report
  <CLAIM-ID>/output.txt       the brief's output format (score, reasons, categories)
  all_results.json            every result in one file
  SHOWCASE.md                 input -> output summary table
  workflow.mmd                Mermaid diagram of the agent graph
  showcase.html               self-contained, offline web UI with all results embedded
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from app.agents.base import AGENT_REGISTRY, CATEGORIES
from app.config import APP_DIR, LOW_RISK_MAX, MEDIUM_RISK_MAX, ML_WEIGHT, OUTPUTS_DIR, RULE_WEIGHT, SAMPLES_DIR
from app.graph import NODES, engine_name, mermaid, run_claim
from app.ml.model import load_model
from app.report_html import render_report_html
from app.tools.utils import inr


def run_all(verbose: bool = True) -> list[dict]:
    index = json.loads((SAMPLES_DIR / "index.json").read_text())
    results = []
    for s in index:
        folder = SAMPLES_DIR / s["claim_id"]
        files = sorted(folder.glob("*.pdf"))
        r = run_claim(files, claim_id=s["claim_id"], source="sample")
        out = OUTPUTS_DIR / s["claim_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (out / "report.html").write_text(render_report_html(r), encoding="utf-8")
        (out / "output.txt").write_text(r["output_text"] + "\n", encoding="utf-8")
        results.append(r)
        if verbose:
            print(f"  {r['claim_id']}  score={str(r['fraud_score']):>5}  {r['status']:<18} {s['title']}")
    (OUTPUTS_DIR / "all_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (OUTPUTS_DIR / "workflow.mmd").write_text(mermaid(), encoding="utf-8")
    _write_markdown(index, results)
    _write_static_ui(index, results)
    return results


def _write_markdown(index: list[dict], results: list[dict]) -> None:
    lines = [
        "# ClaimGuard AI - Showcase: inputs and outputs",
        "",
        f"Engine: **{engine_name()}**. Every sample was processed by the full multi-agent pipeline. "
        "Input documents are in `data/sample_claims/<CLAIM-ID>/`, outputs in `outputs/<CLAIM-ID>/`.",
        "",
        "| Claim | Scenario (input) | Claimed | Fraud score | Band | Decision | Net payable |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for s, r in zip(index, results):
        pay = (r.get("settlement") or {}).get("payable")
        lines.append(f"| {r['claim_id']} | {s['title']} | {inr(r['claim_summary'].get('claimed_amount'))} | "
                     f"{'-' if r['fraud_score'] is None else r['fraud_score']} | {r['risk_band'] or '-'} | "
                     f"{r['status']} | {'-' if pay is None else inr(pay)} |")
    for s, r in zip(index, results):
        lines += ["", f"## {r['claim_id']} - {s['title']}", "",
                  f"**Input documents:** {', '.join(s['files'])}  ",
                  f"**Designed to show:** {s['expected']}", "", "```text", r["output_text"], "```", "",
                  f"**Case note:** {r['narrative']}"]
        if r.get("settlement"):
            lines += ["", "**Settlement:**", ""] + [f"- {l['label']}: {inr(l['amount'])}" for l in r["settlement"]["lines"]]
        if r.get("siu"):
            lines += ["", f"**SIU case {r['siu']['case_id']}** ({r['siu']['priority']}):", ""] + [f"- {t['task']}" for t in r["siu"]["tasks"]]
        if r.get("doc_request"):
            lines += ["", "**Documents requested:**", ""] + [f"- {x}" for x in r["doc_request"]["required"]]
    (OUTPUTS_DIR / "SHOWCASE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_static_ui(index: list[dict], results: list[dict], include_pdfs: bool = True, out: Path | None = None) -> None:
    web = APP_DIR / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    css = (web / "static" / "styles.css").read_text(encoding="utf-8")
    js = (web / "static" / "app.js").read_text(encoding="utf-8")
    pdfs = {}
    for s in index if include_pdfs else []:
        for f in s["files"]:
            b = (SAMPLES_DIR / s["claim_id"] / f).read_bytes()
            pdfs[f"{s['claim_id']}/{f}"] = "data:application/pdf;base64," + base64.b64encode(b).decode()
    runs = [{"run_id": r["run_id"], "claim_id": r["claim_id"], "processed_at": r["processed_at"],
             "patient": r["claim_summary"].get("patient_name"), "hospital": r["claim_summary"].get("hospital_name"),
             "diagnosis": r["claim_summary"].get("diagnosis"), "claimed_amount": r["claim_summary"].get("claimed_amount"),
             "fraud_score": r["fraud_score"], "risk_band": r["risk_band"], "status": r["status"],
             "payable": (r.get("settlement") or {}).get("payable")} for r in results]
    data = {
        "samples": index,
        "results": {r["claim_id"]: r for r in results},
        "reports": {r["claim_id"]: render_report_html(r) for r in results},
        "pdfs": pdfs,
        "runs": runs,
        "workflow": {"engine": engine_name(), "mermaid": mermaid(),
                     "agents": [{"node": k, **AGENT_REGISTRY[k]} for k in NODES], "categories": CATEGORIES,
                     "scoring": {"rule_weight": RULE_WEIGHT, "ml_weight": ML_WEIGHT, "low_max": LOW_RISK_MAX, "medium_max": MEDIUM_RISK_MAX}},
        "model": load_model()["metrics"],
    }
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    html = html.replace('<link rel="stylesheet" href="/static/styles.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="/static/app.js"></script>',
                        f"<script>window.__STATIC__ = {payload};</script>\n<script>\n{js}\n</script>")
    html = re.sub(r"<title>(.*?)</title>", r"<title>\1 (showcase)</title>", html, count=1)
    (out or OUTPUTS_DIR / "showcase.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    run_all()
