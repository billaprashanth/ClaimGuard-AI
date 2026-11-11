"""Stage 2: Knowledge Retrieval Agent - grounds the claim in policy, provider, clinical & history data."""
from __future__ import annotations

from app.agents.base import agent, finding
from app.tools import knowledge_base as kb
from app.tools.utils import parse_date


@agent("Knowledge Retrieval Agent", "Looks up policy, insured member, provider registry, clinical KB and claim history", "knowledge")
def knowledge_agent(state: dict) -> dict:
    c = state.get("claim", {})
    F = []

    policy = kb.find_policy(c.get("policy_number"))
    member, member_score = (kb.find_member(policy, c.get("patient_name")) if policy else (None, 0.0))
    if not policy:
        F.append(finding("POLICY_NOT_FOUND", "DOCUMENT_ISSUES", "CRITICAL",
                         f"Policy number '{c.get('policy_number')}' not found in the policy administration system"))
    elif not member:
        F.append(finding("NOT_INSURED_MEMBER", "DOCUMENT_ISSUES", "CRITICAL",
                         f"Patient '{c.get('patient_name')}' is not an insured member of policy {policy['policy_number']}"))
    elif c.get("patient_dob") and parse_date(member["dob"]) != parse_date(c["patient_dob"]):
        F.append(finding("DOB_MISMATCH", "DOCUMENT_ISSUES", "HIGH",
                         f"Date of birth on claim ({c['patient_dob']}) differs from policy records ({member['dob']})"))

    hospital, how = kb.find_hospital(c.get("hospital_name"), c.get("hospital_reg_no"))
    dx_key, dx, dx_how = kb.find_diagnosis(c.get("diagnosis"), c.get("icd10"))
    dx_cf_key, _, _ = kb.find_diagnosis(c.get("diagnosis_claim_form"))
    icd_key = None
    if c.get("icd10"):
        icd_key, _, h = kb.find_diagnosis(None, c.get("icd10"))
        icd_key = icd_key if h == "icd10" else None
    text_key, _, _ = kb.find_diagnosis(c.get("diagnosis"))

    history = kb.past_claims(policy["policy_number"]) if policy else []
    registry = kb.registry_matches(c.get("bill_no"), c.get("patient_name"), c.get("patient_dob"))

    context = {
        "policy": policy,
        "member": member,
        "member_match": round(member_score, 2),
        "hospital": hospital,
        "hospital_match": how,
        "diagnosis_key": dx_key,
        "diagnosis_kb": dx,
        "diagnosis_match": dx_how,
        "diagnosis_claim_form_key": dx_cf_key,
        "diagnosis_text_key": text_key,
        "icd10_key": icd_key,
        "past_claims": history,
        "registry_matches": registry,
    }
    bits = [
        f"policy {'found' if policy else 'NOT found'}",
        f"member {'verified' if member else 'NOT verified'}",
        f"hospital {hospital['hospital_id'] if hospital else 'not in registry'}",
        f"diagnosis -> {dx_key or 'unknown'} ({dx_how})",
        f"{len(history)} past claim(s)",
        f"{len(registry)} registry hit(s)",
    ]
    return {"context": context, "findings": F, "_summary": "; ".join(bits) + "."}
