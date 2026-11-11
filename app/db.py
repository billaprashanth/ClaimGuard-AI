"""SQLite persistence for processed claims (audit trail). Standard library only."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from app.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claim_runs (
    run_id TEXT PRIMARY KEY,
    claim_id TEXT,
    processed_at TEXT,
    patient TEXT,
    hospital TEXT,
    diagnosis TEXT,
    claimed_amount REAL,
    fraud_score REAL,
    risk_band TEXT,
    status TEXT,
    payable REAL,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_claim ON claim_runs(claim_id);
"""


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def save_run(report: dict) -> None:
    c = report.get("claim_summary", {})
    d = report.get("decision") or {}
    with closing(_conn()) as con, con:
        con.execute(
            "INSERT OR REPLACE INTO claim_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (report["run_id"], report["claim_id"], report["processed_at"], c.get("patient_name"),
             c.get("hospital_name"), c.get("diagnosis"), c.get("claimed_amount"), report.get("fraud_score"),
             report.get("risk_band"), report.get("status"), (report.get("settlement") or {}).get("payable"),
             json.dumps(report, default=str)),
        )


def list_runs(limit: int = 100) -> list[dict]:
    with closing(_conn()) as con:
        rows = con.execute(
            "SELECT run_id, claim_id, processed_at, patient, hospital, diagnosis, claimed_amount, fraud_score, "
            "risk_band, status, payable FROM claim_runs ORDER BY processed_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with closing(_conn()) as con:
        row = con.execute("SELECT result_json FROM claim_runs WHERE run_id=?", (run_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def stats() -> dict:
    with closing(_conn()) as con:
        rows = con.execute("SELECT status, COUNT(*) n, SUM(claimed_amount) amt FROM claim_runs GROUP BY status").fetchall()
    return {r["status"]: {"count": r["n"], "amount": r["amt"]} for r in rows}
