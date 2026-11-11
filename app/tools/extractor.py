"""Document classification + structured field extraction (rule/regex based, no LLM).

Each claim document is classified, then mapped to a typed dictionary of fields.
Line items of the hospital bill are parsed into a list of dicts.
"""
from __future__ import annotations

import re
from typing import Optional

from app.tools.utils import parse_date, parse_money

DOC_TYPES = ("claim_form", "hospital_bill", "discharge_summary", "prescription", "lab_report")

_CLASS_KEYWORDS = {
    "claim_form": ["claim form", "claimant", "claimed amount", "declaration by the insured", "part a"],
    "hospital_bill": ["final bill", "hospital bill", "bill no", "grand total", "net payable", "particulars"],
    "discharge_summary": ["discharge summary", "course in hospital", "condition at discharge", "final diagnosis"],
    "prescription": ["prescription", "rx", "sig:", "tablet", "cap."],
    "lab_report": ["laboratory report", "test name", "reference range", "specimen"],
}

FIELD_LABELS: dict[str, list[str]] = {
    "claim_no": ["claim reference", "claim no", "claim number"],
    "policy_number": ["policy number", "policy no"],
    "proposer_name": ["proposer name", "primary insured", "policy holder"],
    "patient_name": ["patient name", "name of patient", "insured patient"],
    "patient_dob": ["date of birth", "dob"],
    "patient_age": ["age"],
    "gender": ["gender", "sex"],
    "relationship": ["relationship with proposer", "relationship"],
    "hospital_name": ["hospital name", "name of hospital"],
    "hospital_reg_no": ["hospital registration no", "registration no", "regn no"],
    "admission_date": ["date of admission", "admission date"],
    "discharge_date": ["date of discharge", "discharge date"],
    "diagnosis": ["final diagnosis", "diagnosis", "provisional diagnosis"],
    "icd10": ["icd-10 code", "icd10", "icd code"],
    "claim_type": ["claim type", "type of claim"],
    "claimed_amount": ["total amount claimed", "claimed amount", "amount claimed"],
    "submission_date": ["date of submission", "submission date"],
    "accident": ["injury due to accident", "accident case", "is this an accident"],
    "other_policies": ["other active health policies", "other health insurance"],
    "declared_ped": ["pre-existing disease declared", "any pre-existing disease"],
    "bill_no": ["bill no", "bill number", "invoice no"],
    "bill_date": ["bill date", "invoice date"],
    "ip_no": ["ip no", "uhid", "ipd no"],
    "room_category": ["room category", "ward type"],
    "gross_total": ["grand total", "total bill amount", "net payable"],
    "seal_signature": ["hospital seal & signature", "seal & signature", "seal and signature", "authorised signatory"],
    "treating_doctor": ["treating doctor", "consultant", "attending doctor"],
    "doctor_reg_no": ["doctor registration no", "doctor reg no", "mci/smc reg no", "smc reg no"],
    "procedures": ["procedures performed", "procedure done", "surgery performed"],
    "past_history": ["past history", "history of present illness", "past medical history"],
    "clinical_course": ["course in hospital", "clinical course"],
    "condition_at_discharge": ["condition at discharge"],
}

ITEM_CATEGORIES = ("ROOM", "ICU", "NURSING", "CONSULT", "LAB", "RADIOLOGY", "PHARMACY",
                   "CONSUMABLE", "PROCEDURE", "OT", "IMPLANT", "MISC")
_ITEM_RE = re.compile(
    r"^\s*(\d{1,3})[.)]?\s+(.+?)\s+(" + "|".join(ITEM_CATEGORIES) + r")\s+(\d+)\s+([\d,]+(?:\.\d{1,2})?)\s+([\d,]+(?:\.\d{1,2})?)\s*$"
)


def classify(text: str, filename: str = "") -> tuple[str, float]:
    t = (text or "").lower()
    fn = filename.lower()
    scores = {}
    for dtype, kws in _CLASS_KEYWORDS.items():
        s = sum(2 if kw in t[:400] else 1 for kw in kws if kw in t)
        if dtype.replace("_", "") in fn.replace("_", "").replace("-", ""):
            s += 2
        scores[dtype] = s
    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    if scores[best] == 0:
        return "unknown", 0.0
    return best, round(scores[best] / total, 2)


def _find(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        pat = re.compile(r"(?im)^[ \t]*" + re.escape(label) + r"[ \t]*[:\-][ \t]*(.*)$")
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            return val if val else ""
    return None


def _multiline(text: str, label: str) -> Optional[str]:
    """Capture a paragraph after a heading line such as 'Course in Hospital:'."""
    pat = re.compile(r"(?is)" + re.escape(label) + r"\s*:\s*(.+?)(?:\n\s*\n|\n[A-Z][A-Za-z /&()-]{3,40}:|\Z)")
    m = pat.search(text)
    if not m:
        return None
    para = re.sub(r"\s+", " ", m.group(1)).strip()
    return re.sub(r"(\s+(HOSPITAL|SEAL))+\s*$", "", para)


def parse_line_items(text: str) -> list[dict]:
    items = []
    for line in (text or "").splitlines():
        m = _ITEM_RE.match(line)
        if not m:
            continue
        sno, desc, cat, qty, rate, amount = m.groups()
        items.append({
            "sno": int(sno),
            "description": desc.strip(),
            "category": cat,
            "qty": int(qty),
            "rate": parse_money(rate),
            "amount": parse_money(amount),
        })
    return items


def extract_fields(doc_type: str, text: str, json_data: Optional[dict] = None) -> dict:
    """Return a dict of extracted fields for the document."""
    if json_data:  # already-structured input (API / JSON upload) - skip text parsing, still normalise
        fields = dict(json_data.get("fields", json_data))
        fields.pop("document_type", None)
        items = fields.get("line_items") or []
        fields["line_items"] = [{
            "sno": it.get("sno", i), "description": str(it.get("description", "")),
            "category": str(it.get("category", "MISC")).upper(), "qty": int(it.get("qty", 1)),
            "rate": parse_money(it.get("rate")) or 0.0,
            "amount": parse_money(it.get("amount")) or (parse_money(it.get("rate")) or 0.0) * int(it.get("qty", 1)),
        } for i, it in enumerate(items, 1)]
        if doc_type != "hospital_bill" and not items:
            fields.pop("line_items")
    else:
        fields = {}
        for key, labels in FIELD_LABELS.items():
            val = _find(text, labels)
            if val is not None:
                fields[key] = val

        # Long free-text sections
        for key, label in (("clinical_course", "Course in Hospital"), ("past_history", "Past History")):
            para = _multiline(text, label)
            if para:
                fields[key] = para

        if doc_type in ("hospital_bill", "discharge_summary"):
            first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            if first and "claim form" not in first.lower():
                fields.setdefault("hospital_name", first)

        if doc_type == "hospital_bill":
            fields["line_items"] = parse_line_items(text)
            if "bill_no" in fields and fields["bill_no"]:
                fields["bill_no"] = fields["bill_no"].split()[0]

    # Normalise types
    for k in ("admission_date", "discharge_date", "submission_date", "bill_date", "patient_dob"):
        if fields.get(k):
            d = parse_date(fields[k])
            fields[k] = d.isoformat() if d else fields[k]
    for k in ("claimed_amount", "gross_total"):
        if fields.get(k):
            fields[k] = parse_money(fields[k])
    if fields.get("patient_age"):
        m = re.search(r"\d+", str(fields["patient_age"]))
        fields["patient_age"] = int(m.group(0)) if m else None
    return fields
