from pathlib import Path

import pytest

from app.graph import mermaid, run_claim

EXPECTED = {
    "CLM-2026-1001": ("AUTO_APPROVE", "LOW"),
    "CLM-2026-1002": ("AUTO_APPROVE", "LOW"),
    "CLM-2026-1003": ("HUMAN_REVIEW", "MEDIUM"),
    "CLM-2026-1004": ("SIU_INVESTIGATION", "HIGH"),
    "CLM-2026-1005": ("HUMAN_REVIEW", "MEDIUM"),
    "CLM-2026-1006": ("PENDING_DOCUMENTS", None),
    "CLM-2026-1007": ("SIU_INVESTIGATION", "HIGH"),
}


@pytest.mark.parametrize("claim_id,expected", EXPECTED.items())
def test_sample_outcomes(sample_files, claim_id, expected):
    r = run_claim(sample_files(claim_id), claim_id=claim_id)
    assert (r["status"], r["risk_band"]) == expected
    assert not r["errors"]
    assert r["output_text"]


def test_fraud_case_details(sample_files):
    r = run_claim(sample_files("CLM-2026-1004"))
    cats = {c["category"] for c in r["triggered_categories"]}
    assert {"BILL_AMOUNT", "SINGLE_ITEM", "DIAGNOSIS_MISMATCH", "HOSPITAL_RISK", "DOCUMENT_ISSUES",
            "SUSPICIOUS_TIMING", "OVERCHARGING", "TREATMENT_DURATION"} <= cats
    assert r["fraud_score"] > 65 and r["siu"]["payment_hold"]
    assert "Fraud Score:" in r["output_text"] and "Triggered Categories:" in r["output_text"]


def test_duplicate_bill_is_critical(sample_files):
    r = run_claim(sample_files("CLM-2026-1007"))
    assert any(f["code"] == "DUPLICATE_CLAIM" and f["severity"] == "CRITICAL" for f in r["findings"])


def test_room_rent_proportionate_deduction(sample_files):
    r = run_claim(sample_files("CLM-2026-1002"))
    assert r["settlement"]["payable"] == 67200.0  # 1,28,300 - 500 non-payable - 60% of 1,01,000 associated


def test_engines_agree(sample_files):
    for cid in ("CLM-2026-1003", "CLM-2026-1004", "CLM-2026-1006"):
        a = run_claim(sample_files(cid), engine="langgraph")
        b = run_claim(sample_files(cid), engine="builtin")
        assert (a["status"], a["fraud_score"]) == (b["status"], b["fraud_score"])


def test_parallel_agents_all_ran(sample_files):
    r = run_claim(sample_files("CLM-2026-1001"))
    nodes = [t["node"] for t in r["agent_trace"]]
    for n in ("policy", "medical", "billing", "provider", "history", "ml_scoring", "decision", "settlement", "report"):
        assert n in nodes
    assert len(nodes) == 14


def test_json_documents():
    folder = Path(__file__).resolve().parent.parent / "examples" / "json_claim"
    r = run_claim(sorted(folder.glob("*.json")))
    assert r["status"] == "AUTO_APPROVE" and r["claim_summary"]["patient_name"] == "Swathi Kumar"


def test_mermaid():
    assert "ml_scoring" in mermaid() and "flowchart" in mermaid()
