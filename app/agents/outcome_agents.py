"""Stage 5: outcome agents - settlement computation, SIU investigation plan, final report."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.agents.base import SEVERITY_ORDER, agent
from app.tools import knowledge_base as kb
from app.tools.utils import inr

ASSOCIATED = ("ROOM", "NURSING", "CONSULT", "OT", "PROCEDURE", "MISC")  # proportionate-deduction scope (IRDAI)


@agent("Settlement Agent", "Computes admissible amount: non-payables, room-rent proportionate deduction, co-pay, sum insured", "settlement")
def settlement_agent(state: dict) -> dict:
    c, ctx, d = state.get("claim", {}), state.get("context", {}), state.get("decision", {})
    policy = ctx.get("policy") or {}
    items = c.get("line_items", [])
    claimed = c.get("claimed_amount") or c.get("billed_total") or 0
    billed = min(claimed, c.get("line_items_total") or claimed) if items else claimed
    lines = [{"label": "Amount claimed", "amount": claimed}]
    if billed < claimed:
        lines.append({"label": "Restricted to itemised bill total", "amount": -(claimed - billed)})
    notes = []

    if d.get("status") == "NOT_ADMISSIBLE":
        lines.append({"label": "Not admissible under policy terms", "amount": -billed})
        return {"settlement": {"payable": 0, "lines": lines, "status": "REPUDIATED", "notes": d["coverage"].get("issues", [])},
                "_summary": "Claim not admissible - payable ₹0."}

    nonpay_pat = kb.tariffs()["non_payable_patterns"]
    nonpay = [it for it in items if any(p in it["description"].lower() for p in nonpay_pat)]
    np_total = sum(it["amount"] for it in nonpay)
    if np_total:
        lines.append({"label": "Non-payable items (" + ", ".join(it["description"] for it in nonpay) + ")", "amount": -np_total})

    prop_ded = 0.0
    if policy.get("room_rent_cap_pct"):
        elig = policy["sum_insured"] * policy["room_rent_cap_pct"] / 100
        rooms = [it for it in items if it["category"] == "ROOM"]
        if rooms:
            actual = max(it["rate"] for it in rooms)
            if actual > elig:
                ratio = elig / actual
                base = sum(it["amount"] for it in items if it["category"] in ASSOCIATED and it not in nonpay)
                prop_ded = round(base * (1 - ratio), 2)
                lines.append({"label": f"Proportionate deduction: room {inr(actual)}/day vs eligible {inr(elig)}/day "
                                       f"({ratio:.0%} of associated charges {inr(base)} payable)", "amount": -prop_ded})
                notes.append("Proportionate deduction is not applied to pharmacy, consumables, implants or diagnostics.")
    if policy.get("icu_cap_pct"):
        elig_icu = policy["sum_insured"] * policy["icu_cap_pct"] / 100
        for it in (i for i in items if i["category"] == "ICU" and i["rate"] > elig_icu):
            ded = (it["rate"] - elig_icu) * it["qty"]
            lines.append({"label": f"ICU charges above {inr(elig_icu)}/day limit", "amount": -ded})
            prop_ded += ded

    admissible = max(0.0, billed - np_total - prop_ded)
    copay = round(admissible * policy.get("copay_pct", 0) / 100, 2)
    if copay:
        lines.append({"label": f"Co-payment {policy['copay_pct']}%", "amount": -copay})
    payable = admissible - copay
    available = policy.get("sum_insured", payable) - policy.get("sum_insured_utilised", 0)
    if payable > available:
        lines.append({"label": "Restricted to available sum insured", "amount": -(payable - available)})
        payable = available
    payable = round(payable, 2)
    lines.append({"label": "Net payable", "amount": payable})
    status = "APPROVED" if d.get("status") == "AUTO_APPROVE" else "PROVISIONAL - pending human review"
    if d.get("status") == "HUMAN_REVIEW":
        notes.append("Amount is provisional; a reviewer must confirm before payment is released.")
    return {"settlement": {"payable": payable, "lines": lines, "status": status, "notes": notes,
                           "deductions": round(claimed - payable, 2)},
            "_summary": f"{status}: net payable {inr(payable)} of {inr(claimed)} claimed."}


_SIU_TASKS = {
    "BILL_AMOUNT": "Obtain itemised indoor case papers and compare with treatment actually given",
    "SINGLE_ITEM": "Collect original pharmacy & diagnostic invoices; verify rates against hospital tariff card",
    "DIAGNOSIS_MISMATCH": "Medical officer to review clinical justification; obtain MRI/CT/endoscopy films and reports with timestamps",
    "HOSPITAL_RISK": "Field visit to hospital: verify bed count, ICU/diagnostic facilities, in-patient register for admission dates",
    "CLAIM_HISTORY": "Cross-check previous claims and industry registry; request settlement letter from other insurer",
    "DOCUMENT_ISSUES": "Verify document authenticity with hospital records department; obtain original signed & sealed copies",
    "TREATMENT_DURATION": "Check nursing notes & vitals charts for the full stay to confirm need for hospitalisation",
    "OVERCHARGING": "Reconcile room-days and charges with hospital admission/discharge register",
    "SUSPICIOUS_TIMING": "Verify prior medical history with family physician / pharmacy records (pre-policy consultations)",
}


@agent("SIU Investigation Agent", "Builds a prioritised investigation plan & evidence pack for high-risk claims", "siu")
def siu_agent(state: dict) -> dict:
    d, c = state.get("decision", {}), state.get("claim", {})
    findings = sorted(state.get("findings", []), key=lambda f: SEVERITY_ORDER[f["severity"]])
    cats = [x["category"] for x in d.get("triggered_categories", [])]
    priority = "P1 - Critical" if d.get("fraud_score", 0) >= 85 or d.get("critical_override") else "P2 - High"
    sla = 5 if priority.startswith("P1") else 10
    tasks = [
        "Call the hospital to confirm admission, treating doctor and bill number",
        f"Verify Dr. registration ({c.get('doctor_reg_no') or 'not provided'}) with the State Medical Council",
    ] + [_SIU_TASKS[k] for k in cats if k in _SIU_TASKS] + [
        "Interview patient / family on symptoms, admission and payments made",
        "Compare signatures on claim form, bill and discharge summary",
    ]
    seen, uniq = set(), []
    for t in tasks:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    potential = c.get("claimed_amount") or 0
    return {
        "siu": {
            "case_id": f"SIU-{c.get('claim_id') or state.get('claim_id')}",
            "priority": priority,
            "due_by": (datetime.now() + timedelta(days=sla)).date().isoformat(),
            "payment_hold": True,
            "exposure": potential,
            "tasks": [{"task": t, "status": "OPEN"} for t in uniq],
            "evidence": [{"severity": f["severity"], "category": f["category_label"], "reason": f["reason"]}
                         for f in findings if f["severity"] in ("CRITICAL", "HIGH")][:8],
        },
        "_summary": f"Opened {priority} SIU case with {len(uniq)} task(s); payment of {inr(potential)} on hold.",
    }
