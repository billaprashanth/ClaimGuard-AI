"""Standalone, printable HTML report for one processed claim (no template engine needed)."""
from __future__ import annotations

import html

from app.tools.utils import inr

_CSS = """
body{font:14px/1.55 'Libre Franklin',system-ui,sans-serif;color:#14263B;background:#EEF2F4;margin:0}
.wrap{max-width:900px;margin:24px auto;background:#fff;border:1px solid #C5D0D8;padding:36px 44px}
h1,h2{font-family:'Zilla Slab',Georgia,serif;margin:.2em 0}h1{font-size:28px}h2{font-size:19px;margin-top:28px;border-bottom:2px solid #14263B;padding-bottom:4px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{padding:6px 8px;border-bottom:1px solid #DDE4E9;text-align:left;vertical-align:top}
th{font-weight:600;background:#F4F7F9}.num{text-align:right}.sev{font-weight:700;font-size:12px}
.CRITICAL{color:#7A1410}.HIGH{color:#B3261E}.MEDIUM{color:#8A5A12}.LOW{color:#4A5A68}
.stamp{display:inline-block;border:3px double currentColor;padding:6px 14px;font:700 20px 'Zilla Slab',serif;letter-spacing:.06em;transform:rotate(-3deg);margin:8px 0}
.LOWb{color:#2E7D5B}.MEDIUMb{color:#B7791F}.HIGHb{color:#B3261E}.NAb{color:#4B3B8F}
pre{background:#F4F7F9;border:1px solid #DDE4E9;padding:12px;white-space:pre-wrap;font-size:13px}
.meta{color:#4A5A68}@media print{body{background:#fff}.wrap{border:0;margin:0}}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def render_report_html(r: dict) -> str:
    c = r.get("claim_summary", {})
    band = r.get("risk_band") or "NA"
    rows = "".join(
        f"<tr><td class='sev {f['severity']}'>{f['severity']}</td><td>{_e(f['category_label'])}</td><td>{_e(f['reason'])}</td><td>{_e(f['agent'])}</td></tr>"
        for f in r.get("findings", []))
    items = "".join(
        f"<tr><td>{i['sno']}</td><td>{_e(i['description'])}</td><td>{i['category']}</td><td class='num'>{i['qty']}</td>"
        f"<td class='num'>{inr(i['rate'])}</td><td class='num'>{inr(i['amount'])}</td></tr>" for i in r.get("line_items", []))
    trace = "".join(
        f"<tr><td>{_e(t['agent'])}</td><td class='num'>{t['duration_ms']:.0f} ms</td><td>{_e(t['summary'])}</td></tr>"
        for t in r.get("agent_trace", []))
    extra = ""
    if r.get("settlement"):
        s = r["settlement"]
        extra += "<h2>Settlement</h2><table>" + "".join(
            f"<tr><td>{_e(l['label'])}</td><td class='num'>{inr(l['amount'])}</td></tr>" for l in s["lines"]) + "</table>"
        extra += f"<p class='meta'>{_e(s['status'])}. {_e(' '.join(s.get('notes', [])))}</p>"
    if r.get("siu"):
        s = r["siu"]
        extra += (f"<h2>SIU investigation - {_e(s['case_id'])}</h2><p>Priority <b>{_e(s['priority'])}</b>, due {s['due_by']}, "
                  f"payment on hold ({inr(s['exposure'])}).</p><ol>" + "".join(f"<li>{_e(t['task'])}</li>" for t in s["tasks"]) + "</ol>")
    if r.get("doc_request"):
        extra += f"<h2>Document request</h2><pre>{_e(r['doc_request']['letter'])}</pre>"
    score = "Not scored" if r.get("fraud_score") is None else f"{r['fraud_score']:.0f} / 100"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claim report {_e(r['claim_id'])}</title><style>{_CSS}</style></head><body><div class="wrap">
<p class="meta">ClaimGuard AI decision report - run {_e(r['run_id'])} - {_e(r['processed_at'])} - engine {_e(r.get('engine'))}</p>
<h1>Claim {_e(r['claim_id'])}</h1>
<div class="stamp {band}b">{_e(r['status'].replace('_', ' '))}</div>
<p><b>Fraud score:</b> {score} ({_e(r.get('risk_label'))})<br><b>Recommendation:</b> {_e(r.get('recommendation'))}</p>
<table><tr><th>Patient</th><td>{_e(c.get('patient_name'))}, {_e(c.get('patient_age'))} {_e(c.get('gender'))}</td><th>Policy</th><td>{_e(c.get('policy_number'))}<br>{_e(c.get('plan'))}</td></tr>
<tr><th>Hospital</th><td>{_e(c.get('hospital_name'))} ({_e(c.get('hospital_tier'))})</td><th>Diagnosis</th><td>{_e(c.get('diagnosis'))} [{_e(c.get('icd10'))}]</td></tr>
<tr><th>Stay</th><td>{_e(c.get('admission_date'))} to {_e(c.get('discharge_date'))} ({_e(c.get('los_days'))} days)</td><th>Claimed</th><td>{inr(c.get('claimed_amount'))} ({_e(c.get('claim_type'))})</td></tr></table>
<h2>Summary</h2><p>{_e(r.get('narrative'))}</p>
<h2>Output</h2><pre>{_e(r.get('output_text'))}</pre>
<h2>Findings</h2><table><tr><th>Severity</th><th>Category</th><th>Reason</th><th>Agent</th></tr>{rows or '<tr><td colspan=4>No findings</td></tr>'}</table>
{extra}
<h2>Bill line items</h2><table><tr><th>#</th><th>Particulars</th><th>Category</th><th class='num'>Qty</th><th class='num'>Rate</th><th class='num'>Amount</th></tr>{items}</table>
<h2>Agent trace</h2><table>{trace}</table>
</div></body></html>"""
