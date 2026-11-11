"""Shared graph state passed between agents (LangGraph `StateGraph` schema).

Keys annotated with a reducer are *accumulated* across agents (parallel branches
can all append findings / trace entries safely); every other key is owned by
exactly one agent.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    out = dict(left or {})
    out.update(right or {})
    return out


class ClaimState(TypedDict, total=False):
    # ---- input
    run_id: str
    claim_id: str
    source: str                      # "sample" | "upload" | "json"
    input_files: list[str]
    # ---- document stage
    documents: dict[str, Any]        # doc_type -> {file, fields, meta, forensic_flags}
    unclassified: list[dict]
    claim: dict[str, Any]            # consolidated claim record
    cross_doc: dict[str, Any]        # raw values per document for consistency checks
    validation: dict[str, Any]
    doc_request: dict[str, Any]
    # ---- context (knowledge retrieval)
    context: dict[str, Any]          # policy, member, hospital, diagnosis KB, history
    # ---- analysis (accumulated by parallel agents)
    findings: Annotated[list, operator.add]
    agent_outputs: Annotated[dict, merge_dicts]
    trace: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]
    # ---- scoring & decision
    ml: dict[str, Any]
    decision: dict[str, Any]
    settlement: dict[str, Any]
    siu: dict[str, Any]
    # ---- output
    report: dict[str, Any]
