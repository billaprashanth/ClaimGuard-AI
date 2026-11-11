"""Stage 1 agents: intake, document classification, extraction, validation, document request."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from app.agents.base import agent, finding
from app.config import CLAIM_SUBMISSION_DAYS
from app.tools.document_reader import forensic_flags, read_document
from app.tools.extractor import classify, extract_fields
from app.tools.utils import inr, parse_date, similarity

MANDATORY_DOCS = ("claim_form", "hospital_bill", "discharge_summary")
DOC_LABELS = {
    "claim_form": "Duly filled & signed claim form (Part A)",
    "hospital_bill": "Original final hospital bill with itemised break-up",
    "discharge_summary": "Discharge summary signed by the treating doctor",
    "prescription": "Discharge prescription",
    "lab_report": "Investigation / lab reports",
}


# --------------------------------------------------------------------------- 1. Intake
@agent("Claim Intake Agent", "Registers the claim, assigns a run id and collects input documents", "intake")
def intake_agent(state: dict) -> dict:
    files = [str(Path(f)) for f in state.get("input_files", [])]
    existing = [f for f in files if Path(f).exists()]
    missing = sorted(set(files) - set(existing))
    claim_id = state.get("claim_id") or (Path(existing[0]).parent.name if existing else "CLAIM")
    out = {
        "run_id": state.get("run_id") or f"RUN-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}",
        "claim_id": claim_id,
        "input_files": existing,
        "agent_outputs": {"intake": {"received": len(files), "readable": len(existing), "missing_files": missing}},
        "_summary": f"Registered claim {claim_id} with {len(existing)} document(s).",
    }
    if missing:
        out["errors"] = [f"File not found: {m}" for m in missing]
    return out


# --------------------------------------------------------------------------- 2. Classification
@agent("Document Classifier Agent", "Reads every file (PDF/TXT/JSON/image) and identifies the document type", "classify")
def classifier_agent(state: dict) -> dict:
    documents, unclassified = {}, []
    for f in state.get("input_files", []):
        doc = read_document(f)
        if doc.get("json") and doc["json"].get("document_type"):
            dtype, conf = doc["json"]["document_type"], 1.0
        else:
            dtype, conf = classify(doc.get("text", ""), doc["file"])
        meta = doc.get("metadata", {})
        record = {
            "file": doc["file"],
            "path": doc["path"],
            "doc_type": dtype,
            "confidence": conf,
            "pages": doc.get("pages", 0),
            "chars": len(doc.get("text", "")),
            "text": doc.get("text", ""),
            "json": doc.get("json"),
            "metadata": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in meta.items()},
            "forensic_flags": forensic_flags(meta),
            "error": doc.get("error"),
        }
        if dtype == "unknown" or doc.get("error"):
            unclassified.append(record)
        elif dtype in documents and documents[dtype]["confidence"] >= conf:
            unclassified.append({**record, "note": f"duplicate {dtype}"})
        else:
            documents[dtype] = record
    found = ", ".join(sorted(documents)) or "none"
    return {
        "documents": documents,
        "unclassified": [{k: v for k, v in u.items() if k not in ("text", "json")} for u in unclassified],
        "_summary": f"Identified {len(documents)} document type(s): {found}."
                    + (f" {len(unclassified)} file(s) unclassified." if unclassified else ""),
    }


# --------------------------------------------------------------------------- 3. Extraction
CROSS_FIELDS = ("patient_name", "admission_date", "discharge_date", "diagnosis", "hospital_name", "hospital_reg_no")


@agent("Data Extraction Agent", "Extracts structured fields & bill line items and builds one consolidated claim record", "extract")
def extraction_agent(state: dict) -> dict:
    docs = state.get("documents", {})
    per_doc = {}
    for dtype, d in docs.items():
        per_doc[dtype] = extract_fields(dtype, d.get("text", ""), d.get("json"))

    cf = per_doc.get("claim_form", {})
    bill = per_doc.get("hospital_bill", {})
    ds = per_doc.get("discharge_summary", {})

    def pick(key, *sources):
        for s in sources:
            v = s.get(key)
            if v not in (None, ""):
                return v
        return None

    items = bill.get("line_items", []) or []
    adm = parse_date(pick("admission_date", ds, bill, cf))
    dis = parse_date(pick("discharge_date", ds, bill, cf))
    claim = {
        "claim_id": pick("claim_no", cf) or state.get("claim_id"),
        "policy_number": pick("policy_number", cf, bill, ds),
        "proposer_name": pick("proposer_name", cf),
        "patient_name": pick("patient_name", cf, bill, ds),
        "patient_dob": pick("patient_dob", cf),
        "patient_age": pick("patient_age", cf, ds, bill),
        "gender": pick("gender", cf, ds),
        "relationship": pick("relationship", cf),
        "hospital_name": pick("hospital_name", bill, ds, cf),
        "hospital_reg_no": pick("hospital_reg_no", bill, ds),
        "admission_date": adm.isoformat() if adm else None,
        "discharge_date": dis.isoformat() if dis else None,
        "los_days": (dis - adm).days if adm and dis else None,
        "diagnosis": pick("diagnosis", ds, cf),
        "diagnosis_claim_form": cf.get("diagnosis"),
        "icd10": pick("icd10", ds),
        "claim_type": pick("claim_type", cf) or "Reimbursement",
        "claimed_amount": pick("claimed_amount", cf),
        "submission_date": pick("submission_date", cf),
        "accident": str(pick("accident", cf) or "No").strip().lower().startswith("y"),
        "other_policies_declared": pick("other_policies", cf),
        "ped_declared_on_claim": pick("declared_ped", cf),
        "bill_no": pick("bill_no", bill),
        "bill_date": pick("bill_date", bill),
        "room_category": pick("room_category", bill),
        "billed_total": bill.get("gross_total"),
        "line_items": items,
        "line_items_total": round(sum(i["amount"] or 0 for i in items), 2),
        "seal_on_bill": bill.get("seal_signature"),
        "seal_on_discharge": ds.get("seal_signature"),
        "treating_doctor": ds.get("treating_doctor"),
        "doctor_reg_no": ds.get("doctor_reg_no"),
        "procedures": ds.get("procedures"),
        "past_history": ds.get("past_history"),
        "clinical_course": ds.get("clinical_course"),
    }
    cross = {f: {dt: per_doc[dt].get(f) for dt in per_doc if per_doc[dt].get(f) not in (None, "")} for f in CROSS_FIELDS}
    filled = sum(1 for k, v in claim.items() if v not in (None, "", []))
    return {
        "claim": claim,
        "cross_doc": cross,
        "agent_outputs": {"extraction": {"fields_per_document": {k: len(v) for k, v in per_doc.items()},
                                         "line_items": len(items), "claim_fields_filled": filled}},
        "_summary": f"Extracted {filled} claim fields and {len(items)} bill line items "
                    f"(billed {inr(claim['billed_total'])}, claimed {inr(claim['claimed_amount'])}).",
    }


# --------------------------------------------------------------------------- 4. Validation
def _seal_missing(v) -> bool:
    return v is None or str(v).strip().lower().startswith(("not", "no", "absent", "nil", "-"))


@agent("Document Validation Agent", "Checks completeness, cross-document consistency, bill arithmetic & PDF forensics", "validate")
def validation_agent(state: dict) -> dict:
    docs = state.get("documents", {})
    c = state.get("claim", {})
    cross = state.get("cross_doc", {})
    F, checks = [], []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        return passed

    missing_docs = [d for d in MANDATORY_DOCS if d not in docs]
    check("Mandatory documents present", not missing_docs, "Missing: " + ", ".join(missing_docs) if missing_docs else "All present")
    for d in missing_docs:
        F.append(finding("DOC_MISSING", "DOCUMENT_ISSUES", "MEDIUM", f"Mandatory document missing: {DOC_LABELS[d]}", {"document": d}))

    required = {"policy_number": "Policy number", "patient_name": "Patient name", "admission_date": "Admission date",
                "discharge_date": "Discharge date", "diagnosis": "Diagnosis", "billed_total": "Bill total"}
    missing_fields = [label for k, label in required.items() if c.get(k) in (None, "")]
    check("Mandatory fields extracted", not missing_fields, ", ".join(missing_fields) or "All extracted")

    # Bill arithmetic
    if c.get("billed_total") and c.get("line_items"):
        diff = round(c["billed_total"] - c["line_items_total"], 2)
        if check("Bill total tallies with line items", abs(diff) <= 1, f"Grand total {inr(c['billed_total'])} vs items {inr(c['line_items_total'])}"):
            pass
        else:
            F.append(finding("BILL_NOT_TALLY", "DOCUMENT_ISSUES", "HIGH",
                             f"Bill does not tally: grand total {inr(c['billed_total'])} but line items add up to {inr(c['line_items_total'])} ({inr(abs(diff))} {'less' if diff < 0 else 'more'} than the items)",
                             {"grand_total": c["billed_total"], "items_total": c["line_items_total"]}))
    if c.get("claimed_amount") and c.get("billed_total"):
        if not check("Claimed amount within bill amount", c["claimed_amount"] <= c["billed_total"] + 1,
                     f"Claimed {inr(c['claimed_amount'])} vs billed {inr(c['billed_total'])}"):
            F.append(finding("CLAIM_EXCEEDS_BILL", "DOCUMENT_ISSUES", "HIGH",
                             f"Claimed amount {inr(c['claimed_amount'])} exceeds hospital bill {inr(c['billed_total'])}"))

    # Seals & registration numbers
    if "hospital_bill" in docs and not check("Hospital seal & signature on bill", not _seal_missing(c.get("seal_on_bill")), str(c.get("seal_on_bill"))):
        F.append(finding("BILL_NO_SEAL", "DOCUMENT_ISSUES", "MEDIUM", "Hospital bill has no seal / authorised signature"))
    if "discharge_summary" in docs:
        if not check("Seal & signature on discharge summary", not _seal_missing(c.get("seal_on_discharge")), str(c.get("seal_on_discharge"))):
            F.append(finding("DS_NO_SEAL", "DOCUMENT_ISSUES", "MEDIUM", "Discharge summary is not sealed / signed"))
        if not check("Treating doctor registration number", bool(c.get("doctor_reg_no")), c.get("doctor_reg_no") or "blank"):
            F.append(finding("NO_DOCTOR_REG", "DOCUMENT_ISSUES", "MEDIUM",
                             f"Treating doctor's medical council registration number is missing ({c.get('treating_doctor') or 'doctor unnamed'})"))
    regs = {v for v in cross.get("hospital_reg_no", {}).values()}
    if not check("Hospital registration number present & consistent", len(regs) == 1, ", ".join(regs) or "missing"):
        F.append(finding("HOSP_REG_ISSUE", "DOCUMENT_ISSUES", "HIGH" if len(regs) > 1 else "MEDIUM",
                         "Hospital registration number " + ("differs between documents: " + ", ".join(regs) if regs else "not printed on documents")))

    # Cross-document consistency
    names = cross.get("patient_name", {})
    vals = list(names.values())
    worst = min((similarity(a, b) for i, a in enumerate(vals) for b in vals[i + 1:]), default=1.0)
    if not check("Patient name consistent across documents", worst >= 0.75, " | ".join(f"{k}: {v}" for k, v in names.items())):
        F.append(finding("NAME_MISMATCH", "DOCUMENT_ISSUES", "HIGH", "Patient name differs across documents: " +
                         ", ".join(f"{k}='{v}'" for k, v in names.items()), names))
    for fld, label in (("admission_date", "Admission"), ("discharge_date", "Discharge")):
        ds = {k: parse_date(v) for k, v in cross.get(fld, {}).items()}
        uniq = {d for d in ds.values() if d}
        if not check(f"{label} date consistent across documents", len(uniq) <= 1, ", ".join(f"{k}: {v}" for k, v in ds.items())):
            F.append(finding(f"{fld.upper()}_MISMATCH", "DOCUMENT_ISSUES", "HIGH",
                             f"{label} date differs between documents: " + ", ".join(f"{k}={v}" for k, v in ds.items())))
    if c.get("los_days") is not None and c["los_days"] < 0:
        check("Discharge after admission", False, "Discharge precedes admission")
        F.append(finding("DATE_ORDER", "DOCUMENT_ISSUES", "HIGH", "Discharge date is before admission date"))

    # Submission timeliness
    sub, dis = parse_date(c.get("submission_date")), parse_date(c.get("discharge_date"))
    if sub and dis:
        gap = (sub - dis).days
        if not check(f"Claim submitted within {CLAIM_SUBMISSION_DAYS} days of discharge", gap <= CLAIM_SUBMISSION_DAYS, f"{gap} days"):
            F.append(finding("LATE_SUBMISSION", "DOCUMENT_ISSUES", "LOW", f"Claim submitted {gap} days after discharge"))

    # Forensics
    for dtype, d in docs.items():
        ok = check(f"PDF forensic check - {dtype}", not d.get("forensic_flags"), "; ".join(d.get("forensic_flags", [])) or "clean")
        if not ok:
            F.append(finding("DOC_TAMPERED", "DOCUMENT_ISSUES", "CRITICAL",
                             f"Possible document tampering in {d['file']}: " + "; ".join(d["forensic_flags"]),
                             {"file": d["file"], "metadata": d.get("metadata")}))

    blocking = bool(missing_docs) or any(k in missing_fields for k in ("Policy number", "Patient name"))
    passed = sum(1 for x in checks if x["passed"])
    return {
        "validation": {
            "complete": not missing_docs and not missing_fields,
            "blocking": blocking,
            "missing_documents": missing_docs,
            "missing_fields": missing_fields,
            "checks": checks,
            "passed": passed,
            "total": len(checks),
        },
        "findings": F,
        "agent_outputs": {"validation": {"features": {"doc_issue_count": len(F)}}},
        "_summary": f"{passed}/{len(checks)} validation checks passed"
                    + (f"; BLOCKING - missing {', '.join(missing_docs) or ', '.join(missing_fields)}" if blocking else "")
                    + f"; {len(F)} document issue(s).",
    }


# --------------------------------------------------------------------------- 4b. Document request (branch)
@agent("Document Request Agent", "Pauses incomplete claims and drafts a deficiency letter to the claimant", "request_docs")
def doc_request_agent(state: dict) -> dict:
    v = state.get("validation", {})
    c = state.get("claim", {})
    needed = [DOC_LABELS[d] for d in v.get("missing_documents", [])]
    needed += [f"Field not readable: {f}" for f in v.get("missing_fields", [])]
    for f in state.get("findings", []):
        if f["code"] in ("BILL_NO_SEAL", "DS_NO_SEAL", "NO_DOCTOR_REG", "HOSP_REG_ISSUE"):
            needed.append(f"Re-submit: {f['reason']}")
    letter = (
        f"Dear {c.get('proposer_name') or c.get('patient_name') or 'Policyholder'},\n\n"
        f"We have received your claim {c.get('claim_id') or state.get('claim_id')} for treatment at "
        f"{c.get('hospital_name') or 'the hospital'}. To continue processing, please submit the following within 15 days:\n"
        + "\n".join(f"  {i}. {n}" for i, n in enumerate(needed, 1))
        + "\n\nYour claim will be processed as soon as the documents are received.\n\nClaims Team"
    )
    return {
        "doc_request": {"status": "PENDING_DOCUMENTS", "required": needed, "letter": letter, "due_in_days": 15},
        "_summary": f"Claim paused - requested {len(needed)} item(s) from the claimant.",
    }
