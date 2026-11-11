"""Final agent: compiles the explainable claim decision report and persists it."""
from __future__ import annotations

from datetime import datetime

from app.agents.base import SEVERITY_ORDER, agent
from app.db import save_run
from app.llm.narrator import narrate
from app.tools.utils import inr


def attachment_style_text(r: dict) -> str:
    """The exact output format requested in the project brief."""
    if r["status"] == "PENDING_DOCUMENTS":
        return "Status: PENDING DOCUMENTS\nRequired:\n" + "\n".join(f"- {x}" for x in r["doc_request"]["required"])
    band_txt = {"LOW": "Low Risk - Genuine", "MEDIUM": "Medium Risk - Suspicious", "HIGH": "High Risk"}[r["risk_band"]]
    lines = [f"Fraud Score: {r['fraud_score']:.0f} ({band_txt})", "Suspicious Reasons:"]
    lines += [f"- {x}" for x in r["suspicious_reasons"]] or ["- None"]
    lines.append("Triggered Categories:")
    lines += [f"- {x['label']}" for x in r["triggered_categories"]] or ["- None"]
    lines.append(f"Decision: {r['status'].replace('_', ' ')}")
    return "\n".join(lines)


@agent("Report Agent", "Compiles the explainable decision report, narrative and audit record", "report")
def report_agent(state: dict) -> dict:
    c = state.get("claim", {})
    ctx = state.get("context", {})
    d = state.get("decision")
    docs = state.get("documents", {})
    findings = sorted(state.get("findings", []), key=lambda f: (SEVERITY_ORDER[f["severity"]], -f["points"]))
    pending = bool(state.get("doc_request"))
    hosp = ctx.get("hospital") or {}
    report = {
        "run_id": state.get("run_id"),
        "claim_id": c.get("claim_id") or state.get("claim_id"),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "status": "PENDING_DOCUMENTS" if pending else d["status"],
        "fraud_score": None if pending else d["fraud_score"],
        "risk_band": None if pending else d["risk_band"],
        "risk_label": "Not scored" if pending else d["risk_label"],
        "recommendation": "Request missing documents from claimant." if pending else d["recommendation"],
        "suspicious_reasons": [] if pending else d["suspicious_reasons"],
        "triggered_categories": [] if pending else d["triggered_categories"],
        "findings": findings,
        "claim_summary": {
            "patient_name": c.get("patient_name"), "patient_age": c.get("patient_age"), "gender": c.get("gender"),
            "policy_number": c.get("policy_number"), "plan": (ctx.get("policy") or {}).get("plan"),
            "hospital_name": c.get("hospital_name"), "hospital_id": hosp.get("hospital_id"),
            "hospital_tier": hosp.get("tier"), "network": hosp.get("network"),
            "diagnosis": c.get("diagnosis"), "icd10": c.get("icd10"),
            "admission_date": c.get("admission_date"), "discharge_date": c.get("discharge_date"), "los_days": c.get("los_days"),
            "claim_type": c.get("claim_type"), "claimed_amount": c.get("claimed_amount"), "billed_total": c.get("billed_total"),
            "bill_no": c.get("bill_no"), "treating_doctor": c.get("treating_doctor"),
        },
        "line_items": c.get("line_items", []),
        "documents": [{"doc_type": k, "file": v["file"], "pages": v["pages"], "confidence": v["confidence"],
                       "forensic_flags": v["forensic_flags"], "metadata": v["metadata"]} for k, v in docs.items()],
        "unclassified_files": state.get("unclassified", []),
        "validation": state.get("validation"),
        "decision": d,
        "ml": state.get("ml"),
        "settlement": state.get("settlement"),
        "siu": state.get("siu"),
        "doc_request": state.get("doc_request"),
        "agent_trace": state.get("trace", []),
        "errors": state.get("errors", []),
    }
    report["narrative"], report["narrative_source"] = narrate(report)
    report["output_text"] = attachment_style_text(report)
    try:
        save_run(report)
    except Exception as exc:  # persistence must never break the decision
        report["errors"].append(f"DB save failed: {exc}")
    score = "n/a" if pending else f"{report['fraud_score']}"
    return {"report": report,
            "_summary": f"Report ready: status {report['status']}, score {score}, payable "
                        f"{inr((report.get('settlement') or {}).get('payable')) if report.get('settlement') else '-'}."}
