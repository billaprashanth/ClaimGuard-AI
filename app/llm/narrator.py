"""Investigator narrative writer.

Default: deterministic template (no external API, works offline).
Optional: set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY to let Anthropic Claude rewrite the
narrative from the *structured* findings (Claude never decides the score - it only explains it).
"""
from __future__ import annotations

import json
import logging
import os

from app.config import ANTHROPIC_MODEL, LLM_PROVIDER
from app.tools.utils import inr

log = logging.getLogger("claimguard")


def template_narrative(report: dict) -> str:
    c, d = report["claim_summary"], report.get("decision") or {}
    if report["status"] == "PENDING_DOCUMENTS":
        return (f"Claim {report['claim_id']} for {c.get('patient_name')} at {c.get('hospital_name')} cannot be assessed yet: "
                f"{len(report['doc_request']['required'])} required item(s) are missing. The claim has been paused and a "
                f"deficiency letter drafted. Fraud scoring will run automatically once documents are received.")
    cats = ", ".join(x["label"] for x in d.get("triggered_categories", [])[:4]) or "none"
    top = d.get("suspicious_reasons", [])[:3]
    s = (f"Claim {report['claim_id']}: {c.get('patient_name')}, {c.get('diagnosis')} at {c.get('hospital_name')} "
         f"({c.get('los_days')} day stay), claimed {inr(c.get('claimed_amount'))}. "
         f"Fraud score {d['fraud_score']}/100 ({d['risk_label']}); rule engine {d['rule_score']}, ML model {d['ml_score']}. "
         f"Categories triggered: {cats}. ")
    if top:
        s += "Key concerns: " + " | ".join(top) + ". "
    s += f"Decision: {d['status'].replace('_', ' ')} - {d['recommendation']}"
    return s


def llm_narrative(report: dict) -> str | None:
    if LLM_PROVIDER != "anthropic" or not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        payload = {k: report[k] for k in ("claim_summary", "decision", "settlement", "siu") if report.get(k)}
        msg = anthropic.Anthropic().messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=400,
            system="You are a health-insurance claims investigator. Write a concise, factual 4-6 sentence case note "
                   "from the JSON. Do not invent facts or change the score/decision.",
            messages=[{"role": "user", "content": json.dumps(payload, default=str)[:12000]}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:  # never fail the pipeline because of the optional LLM
        log.warning("LLM narrative skipped: %s", exc)
        return None


def narrate(report: dict) -> tuple[str, str]:
    text = llm_narrative(report)
    return (text, f"anthropic:{ANTHROPIC_MODEL}") if text else (template_narrative(report), "template")
