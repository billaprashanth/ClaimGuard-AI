"""Knowledge-retrieval tools.

Plain JSON knowledge bases + deterministic fuzzy lookups. No vector database,
no embeddings: every match is explainable (which alias / which field matched).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Optional

from app.config import KNOWLEDGE_DIR
from app.tools.utils import norm, parse_date, similarity


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    with open(KNOWLEDGE_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def medical_kb() -> dict:
    return _load("medical_kb.json")


def tariffs() -> dict:
    return _load("tariff_benchmarks.json")


def hospitals() -> list[dict]:
    return _load("hospitals.json")["hospitals"]


def policies() -> list[dict]:
    return _load("policies.json")["policies"]


def history() -> dict:
    return _load("claims_history.json")


# ---------------------------------------------------------------- lookups
def find_policy(policy_number: Optional[str]) -> Optional[dict]:
    if not policy_number:
        return None
    key = norm(policy_number).replace(" ", "")
    for p in policies():
        if norm(p["policy_number"]).replace(" ", "") == key:
            return p
    return None


def find_member(policy: dict, patient_name: Optional[str]) -> tuple[Optional[dict], float]:
    best, score = None, 0.0
    for m in policy.get("insured_members", []):
        s = similarity(m["name"], patient_name)
        if s > score:
            best, score = m, s
    return (best, score) if score >= 0.75 else (None, score)


def find_hospital(name: Optional[str], reg_no: Optional[str] = None) -> tuple[Optional[dict], str]:
    """Match by registration number first (strong), then by fuzzy name (weak)."""
    if reg_no:
        rn = norm(reg_no).replace(" ", "")
        for h in hospitals():
            if norm(h["registration_no"]).replace(" ", "") == rn:
                return h, "registration_no"
    best, score = None, 0.0
    for h in hospitals():
        s = similarity(h["name"], name)
        if s > score:
            best, score = h, s
    if best and score >= 0.8:
        return best, f"name~{score:.2f}"
    return None, "not_found"


def find_diagnosis(text: Optional[str], icd10: Optional[str] = None) -> tuple[Optional[str], Optional[dict], str]:
    """Return (canonical_name, kb_entry, how_matched)."""
    dx = medical_kb()["diagnoses"]
    if icd10:
        code = icd10.strip().upper()
        for k, v in dx.items():
            if v["icd10"].upper() == code:
                return k, v, "icd10"
    t = norm(text)
    if not t:
        return None, None, "missing"
    # longest alias contained in the text wins (e.g. "dengue fever" beats "fever")
    best_key, best_len = None, 0
    for k, v in dx.items():
        for alias in v["aliases"] + [k]:
            a = norm(alias)
            if a and (f" {a} " in f" {t} ") and len(a) > best_len:
                best_key, best_len = k, len(a)
    if best_key:
        return best_key, dx[best_key], "alias"
    # fuzzy fallback
    scored = sorted(((similarity(k, t), k) for k in dx), reverse=True)
    if scored and scored[0][0] >= 0.7:
        return scored[0][1], dx[scored[0][1]], f"fuzzy~{scored[0][0]:.2f}"
    return None, None, "unknown"


def past_claims(policy_number: str) -> list[dict]:
    return history().get("policy_claims", {}).get(policy_number, [])


def registry_matches(bill_no: Optional[str], patient: Optional[str], dob: Optional[str]) -> list[dict]:
    out = []
    bn = norm(bill_no).replace(" ", "") if bill_no else None
    d = parse_date(dob) if dob else None
    for rec in history().get("industry_registry", []):
        same_bill = bn and norm(rec["bill_no"]).replace(" ", "") == bn
        same_person = similarity(rec["patient_name"], patient) >= 0.85 and d and parse_date(rec["patient_dob"]) == d
        if same_bill or same_person:
            out.append({**rec, "match_on": "bill_no" if same_bill else "identity"})
    return out


def item_benchmark(description: str) -> Optional[dict]:
    d = description.lower()
    for item in tariffs()["items"]:
        if any(p in d for p in item["patterns"]):
            return item
    return None


def has_term(text: str, term: str) -> bool:
    """Prefix-word match: 'ct' matches 'CT Abdomen' but not 'Contact'; 'anaesthe' matches 'Anaesthesia'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(term.strip().lower()), (text or "").lower()) is not None


def canonical_procedure(term: str) -> str:
    t = term.strip().lower()
    return "ct scan" if t == "ct" else t
