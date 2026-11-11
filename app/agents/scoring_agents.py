"""Stage 4: ML scoring agent (fan-in join) and the Fraud Risk Decision agent."""
from __future__ import annotations

import math
from collections import defaultdict

from app.agents.base import CATEGORIES, SEVERITY_ORDER, agent
from app.config import CRITICAL_FLOOR, LOW_RISK_MAX, MEDIUM_RISK_MAX, ML_WEIGHT, RULE_WEIGHT
from app.ml.model import score as ml_score


def noisy_or(points: list[float]) -> float:
    """Combine independent risk signals: 1 - prod(1 - p). Two MEDIUM (22) -> 39, HIGH+MEDIUM -> 53."""
    p = 1.0
    for pt in points:
        p *= 1 - min(pt, 99) / 100
    return round((1 - p) * 100, 1)


def category_score(points: list[float]) -> float:
    """Diminishing returns inside one category (correlated signals): 1st finding full weight, 2nd half, 3rd quarter..."""
    return noisy_or([p * (0.5 ** i) for i, p in enumerate(sorted(points, reverse=True))])


@agent("ML Risk Scoring Agent", "Gradient-boosting fraud probability + Isolation-Forest anomaly score on 19 engineered features", "ml_scoring")
def ml_agent(state: dict) -> dict:
    ao = state.get("agent_outputs", {})
    c = state.get("claim", {})
    feats: dict = {}
    for name in ("validation", "policy", "medical", "billing", "provider", "history"):
        feats.update((ao.get(name) or {}).get("features", {}))
    feats["days_since_inception_log"] = math.log1p(max(0, feats.pop("days_since_inception", 1500)))
    feats["claim_amount_log"] = math.log1p(max(0, feats.pop("claim_amount", 0) or 0))
    feats["is_reimbursement"] = int(str(c.get("claim_type", "")).lower().startswith("reimb"))
    feats["patient_age"] = c.get("patient_age") or 40
    feats["doc_issue_count"] = feats.get("doc_issue_count", 0)
    res = ml_score(feats)
    drivers = ", ".join(d["label"] for d in res["top_drivers"][:3]) or "no strong drivers"
    return {"ml": res, "_summary": f"Fraud probability {res['fraud_probability']:.2f} (anomaly {res['anomaly_score']:.0f}/100); drivers: {drivers}."}


@agent("Fraud Risk Decision Agent", "Fuses rule findings + ML score into the 0-100 fraud score, risk band and routing decision", "decision")
def decision_agent(state: dict) -> dict:
    findings = sorted(state.get("findings", []), key=lambda f: (SEVERITY_ORDER[f["severity"]], -f["points"]))
    ml = state.get("ml", {})
    coverage = (state.get("agent_outputs", {}).get("policy") or {}).get("coverage", {})

    by_cat = defaultdict(list)
    for f in findings:
        by_cat[f["category"]].append(f)
    cat_scores = {k: category_score([f["points"] for f in v]) for k, v in by_cat.items()}
    rule_score = noisy_or(list(cat_scores.values()))  # independent categories combine with noisy-OR
    ml_part = ml.get("ml_score", 0.0)
    final = RULE_WEIGHT * rule_score + ML_WEIGHT * ml_part
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    if critical:
        final = max(final, CRITICAL_FLOOR + min(25, 5 * (len(critical) - 1)) + rule_score * 0.05)
    final = round(min(100.0, final), 1)

    if final < LOW_RISK_MAX:
        band, label = "LOW", "Genuine"
    elif final <= MEDIUM_RISK_MAX:
        band, label = "MEDIUM", "Suspicious"
    else:
        band, label = "HIGH", "High Fraud Risk"

    categories = sorted(
        ({"category": k, "label": CATEGORIES[k], "score": cat_scores[k], "findings": len(v),
          "max_severity": min((f["severity"] for f in v), key=lambda s: SEVERITY_ORDER[s])} for k, v in by_cat.items()),
        key=lambda x: -x["score"])

    admissible = coverage.get("admissible", True)
    if band == "HIGH":
        status = "SIU_INVESTIGATION"
        rec = "Hold payment. Refer to Special Investigation Unit (SIU) for field verification."
    elif band == "MEDIUM":
        status = "HUMAN_REVIEW"
        rec = "Route to a senior claims assessor / medical officer for manual review before settlement."
    elif not admissible:
        status = "NOT_ADMISSIBLE"
        rec = "Low fraud risk, but the claim is not payable under policy terms: " + "; ".join(coverage.get("issues", []))
    else:
        status = "AUTO_APPROVE"
        rec = "Low fraud risk and admissible. Approve for settlement as computed."
    if band != "LOW" and not admissible:
        rec += " Coverage issues: " + "; ".join(coverage.get("issues", []))

    return {
        "decision": {
            "fraud_score": final,
            "risk_band": band,
            "risk_label": label,
            "status": status,
            "recommendation": rec,
            "rule_score": rule_score,
            "ml_score": ml_part,
            "anomaly_score": ml.get("anomaly_score"),
            "weights": {"rules": RULE_WEIGHT, "ml": ML_WEIGHT},
            "critical_override": bool(critical),
            "triggered_categories": categories,
            "suspicious_reasons": [f["reason"] for f in findings if f["severity"] != "LOW" or band == "LOW"][:12],
            "coverage": coverage,
        },
        "_summary": f"Fraud score {final} ({label}) = {RULE_WEIGHT}x rules {rule_score} + {ML_WEIGHT}x ML {ml_part}"
                    + (" [critical override]" if critical else "") + f" -> {status}.",
    }


def route_after_decision(state: dict) -> str:
    return "siu" if state.get("decision", {}).get("status") == "SIU_INVESTIGATION" else "settlement"


def route_after_validation(state: dict) -> str:
    return "request_docs" if state.get("validation", {}).get("blocking") else "knowledge"
