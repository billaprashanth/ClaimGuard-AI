"""Stage 3: five specialist analyst agents that run IN PARALLEL (LangGraph fan-out).

Each agent owns a slice of the 9 fraud categories, emits explainable findings and
publishes the numeric features the ML scoring agent needs.
"""
from __future__ import annotations

import re
from datetime import timedelta

from app.agents.base import agent, finding
from app.config import (EARLY_CLAIM_DAYS, FREQUENT_CLAIMS_THRESHOLD, FREQUENT_CLAIMS_WINDOW_DAYS,
                        INITIAL_WAITING_DAYS, ITEM_TOLERANCE, PED_WAITING_MONTHS)
from app.tools import knowledge_base as kb
from app.tools.utils import inr, norm, parse_date


TIER_TEXT = {"small_clinic": "small clinic", "mid": "mid-tier hospital", "premium": "premium hospital"}


def _tier(ctx: dict) -> tuple[str, float]:
    tier = (ctx.get("hospital") or {}).get("tier", "mid")
    return tier, kb.tariffs()["tier_multiplier"].get(tier, 1.0)


# =========================================================================== Policy & coverage
@agent("Policy & Coverage Agent", "Waiting periods, policy validity, sum-insured enhancement and pre-existing disease disclosure", "policy")
def policy_agent(state: dict) -> dict:
    c, ctx = state.get("claim", {}), state.get("context", {})
    policy, dx = ctx.get("policy"), ctx.get("diagnosis_kb") or {}
    F, issues = [], []
    adm = parse_date(c.get("admission_date"))
    feats = {"days_since_inception": 1500, "undeclared_ped": 0}
    if not policy or not adm:
        return {"agent_outputs": {"policy": {"coverage": {"admissible": False, "issues": ["Policy could not be verified"]}, "features": feats}},
                "findings": F, "_summary": "Policy unavailable - coverage not verifiable."}

    accident = bool(c.get("accident")) or bool(dx.get("accident"))
    inception = parse_date(policy["first_inception_date"])
    p_start, p_end = parse_date(policy["period_start"]), parse_date(policy["period_end"])
    days = (adm - inception).days
    feats["days_since_inception"] = days

    if policy.get("status") != "ACTIVE" or not (p_start <= adm <= p_end):
        issues.append(f"Admission {adm} outside policy period {p_start} - {p_end} / policy not active")
    if not accident and days < INITIAL_WAITING_DAYS:
        issues.append(f"Initial waiting period: illness claim {days} days after inception (< {INITIAL_WAITING_DAYS} days)")
        F.append(finding("INITIAL_WAITING", "SUSPICIOUS_TIMING", "HIGH",
                         f"Hospitalised only {days} days after buying the policy (initial {INITIAL_WAITING_DAYS}-day waiting period)",
                         {"inception": str(inception), "admission": str(adm)}))
    elif not accident and days < EARLY_CLAIM_DAYS:
        F.append(finding("EARLY_CLAIM", "SUSPICIOUS_TIMING", "MEDIUM", f"Claim within {days} days of policy inception"))
    elif not accident and days < 365:
        F.append(finding("FIRST_YEAR_CLAIM", "SUSPICIOUS_TIMING", "LOW", f"High-value claim in the first policy year ({days} days after inception)"))

    swp = dx.get("specific_waiting_months", 0)
    if swp and days < swp * 30.4 and not accident:
        issues.append(f"Specific-disease waiting period of {swp} months applies to {ctx.get('diagnosis_key')}")
        F.append(finding("SPECIFIC_WAITING", "SUSPICIOUS_TIMING", "MEDIUM",
                         f"{ctx.get('diagnosis_key', '').title()} has a {swp}-month waiting period; policy is {days // 30} months old"))

    prev_si, si = policy.get("previous_sum_insured", 0), policy["sum_insured"]
    since_renewal = (adm - p_start).days
    if prev_si and si > prev_si and since_renewal <= EARLY_CLAIM_DAYS:
        F.append(finding("SI_ENHANCED", "SUSPICIOUS_TIMING", "MEDIUM",
                         f"Claim {since_renewal} days after sum insured was enhanced from {inr(prev_si)} to {inr(si)} at renewal"))

    # Pre-existing disease disclosure: search clinical history for chronic conditions
    hist = f"{c.get('past_history') or ''} {c.get('clinical_course') or ''}".lower()
    neg = re.search(r"(not a known case|no known comorbid|nil significant|^nil)", hist)
    found = []
    if hist.strip() and not neg:
        for cond, kws in kb.medical_kb()["chronic_conditions_ped"].items():
            if any(k in hist for k in kws):
                found.append(cond)
    years = None
    m = re.search(r"(\d+)\s*(?:years|yrs)", hist)
    if m:
        years = int(m.group(1))
    declared = [norm(x) for x in policy.get("declared_peds", [])]
    undeclared = [f for f in found if norm(f) not in declared]
    if undeclared and (years is None or days < years * 365):
        feats["undeclared_ped"] = 1
        dur = f" for {years} years" if years else ""
        F.append(finding("UNDECLARED_PED", "SUSPICIOUS_TIMING", "HIGH",
                         f"Discharge summary records {', '.join(undeclared)}{dur}, but none was declared at proposal; policy is only {days} days old (possible non-disclosure)",
                         {"conditions": undeclared, "declared": policy.get("declared_peds", [])}))
        if days < PED_WAITING_MONTHS * 30.4:
            issues.append(f"Undeclared pre-existing condition(s) ({', '.join(undeclared)}) within {PED_WAITING_MONTHS}-month PED window - refer to underwriting")

    available = si - policy.get("sum_insured_utilised", 0)
    if (c.get("claimed_amount") or 0) > available:
        issues.append(f"Claimed amount exceeds available sum insured {inr(available)}")

    coverage = {"admissible": not issues, "issues": issues, "days_since_inception": days,
                "accident": accident, "sum_insured": si, "available_si": available}
    return {
        "findings": F,
        "agent_outputs": {"policy": {"coverage": coverage, "features": feats}},
        "_summary": ("Admissible" if not issues else f"{len(issues)} coverage issue(s)") +
                    f"; policy {days} days old; {len(F)} timing/disclosure finding(s).",
    }


# =========================================================================== Medical coherence
_RECOVERY_RE = re.compile(r"(?:subsided|settled|resolved|afebrile|normali[sz]ed)\s+(?:on|by|within)\s+(?:day\s+(\d+)|(\d+)\s*hours?)")


@agent("Medical Coherence Agent", "Diagnosis vs treatment consistency, clinically unrelated tests and length-of-stay", "medical")
def medical_agent(state: dict) -> dict:
    c, ctx = state.get("claim", {}), state.get("context", {})
    dx, key = ctx.get("diagnosis_kb"), ctx.get("diagnosis_key")
    F = []
    feats = {"los_ratio": 1.0, "unrelated_item_count": 0, "opd_manageable": 0, "dx_mismatch": 0}
    if not dx:
        F.append(finding("DX_UNKNOWN", "DIAGNOSIS_MISMATCH", "LOW",
                         f"Diagnosis '{c.get('diagnosis')}' not found in clinical knowledge base - medical officer review needed"))
        return {"findings": F, "agent_outputs": {"medical": {"features": feats}}, "_summary": "Diagnosis not in KB."}

    cf_key = ctx.get("diagnosis_claim_form_key")
    if cf_key and cf_key != key:
        feats["dx_mismatch"] = 1
        F.append(finding("DX_FORM_MISMATCH", "DIAGNOSIS_MISMATCH", "HIGH",
                         f"Diagnosis on claim form ('{c.get('diagnosis_claim_form')}') differs from discharge summary ('{c.get('diagnosis')}')"))
    icd_key, text_key = ctx.get("icd10_key"), ctx.get("diagnosis_text_key")
    if icd_key and text_key and icd_key != text_key:
        feats["dx_mismatch"] = 1
        F.append(finding("ICD_MISMATCH", "DIAGNOSIS_MISMATCH", "MEDIUM",
                         f"ICD-10 code {c.get('icd10')} ({icd_key}) does not match written diagnosis ({text_key})"))

    # Clinically unrelated / unjustified items
    hc = kb.medical_kb()["high_cost_diagnostics"]
    unrelated = []
    for it in c.get("line_items", []):
        d = it["description"]
        if any(kb.has_term(d, u) for u in dx["unrelated_items"]) or (
                any(kb.has_term(d, h) for h in hc) and not any(kb.has_term(d, e) for e in dx["expected_items"])):
            unrelated.append(it)
    if unrelated:
        feats["unrelated_item_count"] = len(unrelated)
        total = sum(i["amount"] for i in unrelated)
        names = ", ".join(i["description"] for i in unrelated)
        F.append(finding("UNRELATED_TREATMENT", "DIAGNOSIS_MISMATCH", "HIGH" if len(unrelated) >= 2 else "MEDIUM",
                         f"Treatment does not match diagnosis: {names} ({inr(total)}) not clinically indicated for {key}",
                         {"items": [i["description"] for i in unrelated], "amount": total}))

    # Length of stay
    los = c.get("los_days")
    lo, hi = dx["los"]
    if los is not None:
        feats["los_ratio"] = round(los / max(hi, 1), 2)
        if dx["care_level"] == "OPD_MANAGEABLE":
            feats["opd_manageable"] = 1
            F.append(finding("OPD_AS_IPD", "TREATMENT_DURATION", "MEDIUM",
                             f"In-patient claim for {key}, which is usually managed as OPD (claimed stay {los} days)"))
        if los > hi:
            sev = "HIGH" if los > hi * 1.6 else "MEDIUM"
            F.append(finding("LONG_STAY", "TREATMENT_DURATION", sev,
                             f"Length of stay {los} days exceeds the typical {lo}-{hi} days for {key}", {"los": los, "typical": [lo, hi]}))
        if los == 0 and dx["care_level"] not in ("DAYCARE", "OPD_MANAGEABLE"):
            F.append(finding("SHORT_STAY", "TREATMENT_DURATION", "MEDIUM", "Admission shorter than 24 hours for a non-daycare condition"))
        m = _RECOVERY_RE.search((c.get("clinical_course") or "").lower())
        if m:
            rec_day = int(m.group(1)) if m.group(1) else max(1, int(m.group(2)) // 24)
            idle = los - rec_day
            if idle >= 3:
                F.append(finding("POST_RECOVERY_STAY", "TREATMENT_DURATION", "MEDIUM",
                                 f"Clinical notes show recovery by day {rec_day} but patient was kept {idle} more day(s)",
                                 {"recovered_day": rec_day, "los": los}))
    return {
        "findings": F,
        "agent_outputs": {"medical": {"features": feats, "diagnosis": key, "care_level": dx["care_level"],
                                      "typical_los": dx["los"], "typical_cost": dx["cost"]}},
        "_summary": f"Diagnosis '{key}' ({dx['icd10']}); {len(unrelated)} unrelated item(s); LOS {los} vs typical {lo}-{hi}.",
    }


# =========================================================================== Billing audit
@agent("Billing Audit Agent", "Bill amount vs benchmark, single-item rates, room rent and duplicate charges", "billing")
def billing_agent(state: dict) -> dict:
    c, ctx = state.get("claim", {}), state.get("context", {})
    dx = ctx.get("diagnosis_kb") or {}
    tier, mult = _tier(ctx)
    items = c.get("line_items", [])
    billed = c.get("billed_total") or c.get("line_items_total") or 0
    F = []
    feats = {"bill_ratio": 0.5, "max_item_ratio": 0.0, "room_rent_ratio": 0.0, "duplicate_items": 0, "claim_amount": billed}

    # (A) total bill vs typical cost for diagnosis at this hospital tier
    if dx:
        typical_max = dx["cost"][1] * mult
        ratio = billed / typical_max if typical_max else 0
        feats["bill_ratio"] = round(ratio, 2)
        if ratio > 1.3:
            F.append(finding("BILL_HIGH", "BILL_AMOUNT", "HIGH" if ratio > 2.0 else "MEDIUM",
                             f"Total bill {inr(billed)} is {ratio:.1f}x the typical maximum {inr(typical_max)} for {ctx.get('diagnosis_key')} at a {TIER_TEXT.get(tier, tier)}",
                             {"billed": billed, "typical_max": typical_max, "ratio": round(ratio, 2)}))

    # (B) single item rates vs tariff benchmarks
    over = []
    for it in items:
        if it["category"] in ("ROOM", "ICU"):
            continue
        bm = kb.item_benchmark(it["description"])
        if bm and it["rate"]:
            cap = bm["max_rate"] * mult * ITEM_TOLERANCE
            r = it["rate"] / cap
            feats["max_item_ratio"] = max(feats["max_item_ratio"], round(it["rate"] / (bm["max_rate"] * mult), 2))
            if r > 1:
                over.append((it, bm, cap, r))
    if over:
        worst = max(o[3] for o in over)
        detail = "; ".join(f"{it['description']} {inr(it['rate'])} (benchmark <= {inr(cap)})" for it, bm, cap, r in over)
        F.append(finding("ITEM_OVERPRICED", "SINGLE_ITEM", "HIGH" if (worst > 1.4 or len(over) >= 3) else "MEDIUM",
                         f"{len(over)} item(s) charged above benchmark: {detail}",
                         {"items": [{"item": it["description"], "rate": it["rate"], "cap": round(cap)} for it, _, cap, _ in over]}))
    big = [it for it in items if it["category"] not in ("ROOM", "ICU", "PROCEDURE", "OT", "IMPLANT") and billed and it["amount"] / billed > 0.4]
    for it in big:
        F.append(finding("ITEM_DOMINANT", "SINGLE_ITEM", "MEDIUM",
                         f"Single item '{it['description']}' is {it['amount'] / billed:.0%} of the whole bill ({inr(it['amount'])})"))

    # (C) room rent vs tier benchmark, days billed vs stay, duplicates
    rooms = kb.tariffs()["room_rent_per_day"]
    room_items = [it for it in items if it["category"] in ("ROOM", "ICU")]
    for it in room_items:
        d = it["description"].lower()
        rtype = "icu" if it["category"] == "ICU" else next((k for k in ("deluxe", "semi private", "private", "general ward") if k in d), "private")
        bench = rooms[rtype] * mult
        ratio = it["rate"] / bench
        feats["room_rent_ratio"] = max(feats["room_rent_ratio"], round(ratio, 2))
        if ratio > ITEM_TOLERANCE:
            F.append(finding("ROOM_OVERCHARGE", "OVERCHARGING", "HIGH" if ratio > 1.6 else "MEDIUM",
                             f"{it['description']} at {inr(it['rate'])}/day exceeds {inr(bench)}/day benchmark for a {TIER_TEXT.get(tier, tier)}"))
    los = c.get("los_days")
    room_days = sum(it["qty"] for it in room_items)
    if los is not None and room_items and room_days > los + 1:
        F.append(finding("ROOM_DAYS", "OVERCHARGING", "MEDIUM", f"{room_days} room-days billed for a {los}-day stay"))
    seen, dups = {}, []
    for it in items:
        k = (norm(it["description"]), it["amount"])
        if k in seen:
            dups.append(it)
        seen[k] = it
    if dups:
        feats["duplicate_items"] = len(dups)
        F.append(finding("DUPLICATE_ITEM", "OVERCHARGING", "MEDIUM",
                         "Duplicate charge(s): " + ", ".join(f"{d['description']} {inr(d['amount'])}" for d in dups)))

    # Policy room-rent limit (used by settlement; NOT a fraud signal by itself)
    policy = ctx.get("policy") or {}
    cap_info = None
    room_only = [it for it in room_items if it["category"] == "ROOM"]
    if policy.get("room_rent_cap_pct") and room_only:
        elig = policy["sum_insured"] * policy["room_rent_cap_pct"] / 100
        actual = max(it["rate"] for it in room_only)
        cap_info = {"eligible_per_day": elig, "actual_per_day": actual, "exceeded": actual > elig}
    return {
        "findings": F,
        "agent_outputs": {"billing": {"features": feats, "tier": tier, "tier_multiplier": mult, "room_cap": cap_info,
                                      "items_over_benchmark": len(over)}},
        "_summary": f"Bill {inr(billed)} ratio {feats['bill_ratio']}x typical; {len(over)} overpriced item(s); "
                    f"{len(dups)} duplicate(s).",
    }


# =========================================================================== Provider risk
@agent("Provider Risk Agent", "Hospital blacklist / watchlist, provider risk index, claim spikes, network status", "provider")
def provider_agent(state: dict) -> dict:
    c, ctx = state.get("claim", {}), state.get("context", {})
    h = ctx.get("hospital")
    F = []
    feats = {"hospital_risk": 0.5, "hospital_network": 0, "hospital_small_clinic": 0}
    if not h:
        F.append(finding("HOSP_UNKNOWN", "HOSPITAL_RISK", "MEDIUM",
                         f"Hospital '{c.get('hospital_name')}' (reg. {c.get('hospital_reg_no') or 'n/a'}) is not in the provider registry"))
        return {"findings": F, "agent_outputs": {"provider": {"features": feats}}, "_summary": "Unknown provider."}
    feats = {"hospital_risk": h["risk_rating"], "hospital_network": int(h["network"]),
             "hospital_small_clinic": int(h["tier"] == "small_clinic")}
    if h["blacklisted"]:
        F.append(finding("HOSP_BLACKLISTED", "HOSPITAL_RISK", "CRITICAL", f"{h['name']} is BLACKLISTED: {h['notes']}"))
    elif h["watchlist"]:
        F.append(finding("HOSP_WATCHLIST", "HOSPITAL_RISK", "HIGH", f"{h['name']} is on the fraud watchlist: {h['notes']}"))
    elif h["risk_rating"] >= 0.3:
        F.append(finding("HOSP_RISKY", "HOSPITAL_RISK", "MEDIUM", f"Provider risk index {h['risk_rating']:.2f} for {h['name']}"))
    spike = h["claims_last_90d"] / max(1, h["avg_claims_90d_baseline"])
    if spike >= 1.8:
        F.append(finding("HOSP_SPIKE", "HOSPITAL_RISK", "MEDIUM",
                         f"Claim volume from {h['name']} is {spike:.1f}x its 90-day baseline ({h['claims_last_90d']} vs {h['avg_claims_90d_baseline']})"))
    billed = c.get("billed_total") or 0
    hc = kb.medical_kb()["high_cost_diagnostics"]
    if h["tier"] == "small_clinic":
        adv = [it["description"] for it in c.get("line_items", []) if any(kb.has_term(it["description"], x) for x in hc)]
        if billed > 75000 or adv:
            F.append(finding("SMALL_CLINIC_PREMIUM", "HOSPITAL_RISK", "HIGH",
                             f"{h['beds']}-bed clinic billing like a premium hospital ({inr(billed)}"
                             + (f"; advanced diagnostics billed: {', '.join(adv)}" if adv else "") + ")"))
    if not h["network"] and str(c.get("claim_type", "")).lower().startswith("reimb"):
        F.append(finding("NON_NETWORK", "HOSPITAL_RISK", "LOW", "Non-network hospital - reimbursement claim (no pre-authorisation)"))
    reg = c.get("hospital_reg_no")
    if reg and norm(reg).replace(" ", "") != norm(h["registration_no"]).replace(" ", ""):
        F.append(finding("HOSP_REG_MISMATCH", "HOSPITAL_RISK", "HIGH",
                         f"Registration no. on documents ({reg}) differs from registry ({h['registration_no']})"))
    return {
        "findings": F,
        "agent_outputs": {"provider": {"features": feats, "hospital_id": h["hospital_id"], "tier": h["tier"],
                                       "network": h["network"], "risk_rating": h["risk_rating"]}},
        "_summary": f"{h['name']} ({h['tier']}, {'network' if h['network'] else 'non-network'}, risk {h['risk_rating']:.2f}); {len(F)} finding(s).",
    }


# =========================================================================== Claim history
@agent("Claim History Agent", "Claim frequency, repeated procedures, duplicate bills & multi-insurer claims", "history")
def history_agent(state: dict) -> dict:
    c, ctx = state.get("claim", {}), state.get("context", {})
    adm = parse_date(c.get("admission_date"))
    past = ctx.get("past_claims", [])
    patient = c.get("patient_name")
    F = []
    window = [p for p in past if adm and parse_date(p["date"]) and adm - timedelta(days=FREQUENT_CLAIMS_WINDOW_DAYS) <= parse_date(p["date"]) < adm]
    feats = {"prior_claims_12m": len(window), "registry_duplicate": 0}
    if len(window) >= FREQUENT_CLAIMS_THRESHOLD:
        same_h = {p["hospital_id"] for p in window}
        hosp = ctx.get("hospital") or {}
        note = f", all at the same hospital ({hosp.get('name', next(iter(same_h)))})" if len(same_h) == 1 else ""
        F.append(finding("FREQUENT_CLAIMS", "CLAIM_HISTORY", "HIGH" if len(window) >= 3 else "MEDIUM",
                         f"{len(window)} previous claims in the last 12 months{note}: " +
                         ", ".join(f"{p['date']} {p['diagnosis']} {inr(p['amount'])}" for p in window),
                         {"claims": window}))
    # repeated high-cost procedures across claims
    hc = kb.medical_kb()["high_cost_diagnostics"]
    current = {kb.canonical_procedure(h) for it in c.get("line_items", []) for h in hc if kb.has_term(it["description"], h)}
    for proc in sorted(current):
        n = sum(1 for p in window if any(proc in x for x in p.get("procedures", [])))
        if n >= 1:
            F.append(finding("REPEAT_PROCEDURE", "CLAIM_HISTORY", "MEDIUM",
                             f"{proc.upper()} billed again - also billed in {n} previous claim(s) within 12 months"))
    # industry registry (duplicate bill / undisclosed policies)
    for r in ctx.get("registry_matches", []):
        if r["match_on"] == "bill_no":
            feats["registry_duplicate"] = 1
            F.append(finding("DUPLICATE_CLAIM", "CLAIM_HISTORY", "CRITICAL",
                             f"Duplicate claim: hospital bill {r['bill_no']} was already claimed with {r['insurer']} "
                             f"(policy {r['policy_number']}) on {r['claim_date']} for {inr(r['amount'])} - status {r['status']}",
                             r))
        else:
            F.append(finding("OTHER_POLICY", "CLAIM_HISTORY", "MEDIUM",
                             f"{patient} also holds policy {r['policy_number']} with {r['insurer']} (status of claim there: {r['status']})", r))
    if ctx.get("registry_matches") and str(c.get("other_policies_declared", "")).strip().lower() in ("none", "no", "nil", ""):
        F.append(finding("UNDISCLOSED_POLICY", "CLAIM_HISTORY", "HIGH",
                         "Claim form declares no other health policy, but the industry registry shows another active policy"))
    return {
        "findings": F,
        "agent_outputs": {"history": {"features": feats, "prior_claims": len(past), "prior_claims_12m": len(window),
                                      "registry_hits": len(ctx.get("registry_matches", []))}},
        "_summary": f"{len(window)} claim(s) in last 12 months; {len(ctx.get('registry_matches', []))} registry hit(s).",
    }
