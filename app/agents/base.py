"""Shared agent plumbing: the @agent decorator, findings and the fraud categories."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional

log = logging.getLogger("claimguard")

# The 9 industry fraud categories (see docs/REQUIREMENTS.md, FR-5)
CATEGORIES: dict[str, str] = {
    "BILL_AMOUNT": "Bill Amount",
    "SINGLE_ITEM": "Single Item Charge",
    "DIAGNOSIS_MISMATCH": "Diagnosis Mismatch",
    "HOSPITAL_RISK": "Hospital Pattern Risk",
    "CLAIM_HISTORY": "Patient Claim History",
    "DOCUMENT_ISSUES": "Document Issues",
    "TREATMENT_DURATION": "Treatment Duration Abnormality",
    "OVERCHARGING": "Room Rent / Procedure Overcharging",
    "SUSPICIOUS_TIMING": "Suspicious Timing (new policy)",
}

# Risk points contributed by one finding (combined with a noisy-OR, see decision agent)
SEVERITY_POINTS = {"LOW": 10, "MEDIUM": 22, "HIGH": 40, "CRITICAL": 75}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Registry used by the UI / docs to describe every agent
AGENT_REGISTRY: dict[str, dict[str, str]] = {}


def finding(code: str, category: str, severity: str, reason: str,
            evidence: Optional[dict] = None, agent: str = "") -> dict:
    assert category in CATEGORIES, category
    return {
        "code": code,
        "category": category,
        "category_label": CATEGORIES[category],
        "severity": severity,
        "points": SEVERITY_POINTS[severity],
        "reason": reason,
        "evidence": evidence or {},
        "agent": agent,
    }


def agent(name: str, role: str, node: str) -> Callable:
    """Wrap a node function: timing, error isolation and an entry in the agent trace."""
    AGENT_REGISTRY[node] = {"name": name, "role": role}

    def deco(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        @wraps(fn)
        def wrapper(state: dict) -> dict:
            started = datetime.now()
            t0 = time.perf_counter()
            try:
                out: dict[str, Any] = fn(state) or {}
                status = "completed"
            except Exception as exc:  # one agent failing must not kill the pipeline
                log.exception("Agent %s failed", name)
                out = {"errors": [f"{name}: {type(exc).__name__}: {exc}"]}
                status = "failed"
            for f in out.get("findings", []):
                f.setdefault("agent", name)
                if not f.get("agent"):
                    f["agent"] = name
            summary = out.pop("_summary", "") if isinstance(out, dict) else ""
            out["trace"] = [{
                "node": node,
                "agent": name,
                "role": role,
                "status": status,
                "started_at": started.isoformat(timespec="milliseconds"),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "findings": len(out.get("findings", [])),
                "summary": summary,
            }]
            return out

        wrapper.node = node  # type: ignore[attr-defined]
        return wrapper

    return deco
