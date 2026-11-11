r"""The ClaimGuard multi-agent workflow, built with LangGraph's StateGraph.

                   +--> policy   --+
intake -> classify -> extract -> validate --(complete)--> knowledge --+--> medical  --+--> ml_scoring -> decision --(HIGH)--> siu ------+--> report -> END
                                     |                                +--> billing  --+                            \--(else)--> settlement -+
                                     |                                +--> provider --+
                                     |                                +--> history  --+
                                     \--(blocking)--> request_docs -----------------------------------------------------------------------> report

Engine selection: LangGraph (default, if installed) or the built-in mini engine
(`CLAIMGUARD_ENGINE=builtin`, or automatically when langgraph is not installed).
Both are built from the SAME declarative spec below.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.agents.analyst_agents import billing_agent, history_agent, medical_agent, policy_agent, provider_agent
from app.agents.base import AGENT_REGISTRY
from app.agents.document_agents import (classifier_agent, doc_request_agent, extraction_agent, intake_agent,
                                        validation_agent)
from app.agents.knowledge_agent import knowledge_agent
from app.agents.outcome_agents import settlement_agent, siu_agent
from app.agents.report_agent import report_agent
from app.agents.scoring_agents import decision_agent, ml_agent, route_after_decision, route_after_validation
from app.state import ClaimState

NODES = {
    "intake": intake_agent, "classify": classifier_agent, "extract": extraction_agent, "validate": validation_agent,
    "request_docs": doc_request_agent, "knowledge": knowledge_agent,
    "policy": policy_agent, "medical": medical_agent, "billing": billing_agent, "provider": provider_agent,
    "history": history_agent, "ml_scoring": ml_agent, "decision": decision_agent,
    "settlement": settlement_agent, "siu": siu_agent, "report": report_agent,
}
ANALYSTS = ["policy", "medical", "billing", "provider", "history"]
EDGES = [("START", "intake"), ("intake", "classify"), ("classify", "extract"), ("extract", "validate"),
         ("request_docs", "report"), ("settlement", "report"), ("siu", "report"), ("ml_scoring", "decision"),
         ("report", "END")] + [("knowledge", a) for a in ANALYSTS]
JOINS = [(ANALYSTS, "ml_scoring")]
CONDITIONALS = {
    "validate": (route_after_validation, {"knowledge": "knowledge", "request_docs": "request_docs"}),
    "decision": (route_after_decision, {"siu": "siu", "settlement": "settlement"}),
}


def _build(engine: str):
    if engine == "langgraph":
        from langgraph.graph import END, START, StateGraph
    else:
        from app.mini_graph import END, START, MiniStateGraph as StateGraph
    g = StateGraph(ClaimState)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    m = {"START": START, "END": END}
    for a, b in EDGES:
        g.add_edge(m.get(a, a), m.get(b, b))
    for sources, target in JOINS:
        g.add_edge(list(sources), target)
    for src, (fn, path_map) in CONDITIONALS.items():
        g.add_conditional_edges(src, fn, path_map)
    return g.compile()


def engine_name() -> str:
    want = os.getenv("CLAIMGUARD_ENGINE", "langgraph").lower()
    if want == "langgraph":
        try:
            import langgraph  # noqa: F401
            return "langgraph"
        except ImportError:
            return "builtin"
    return "builtin"


@lru_cache(maxsize=2)
def get_workflow(engine: str | None = None):
    return _build(engine or engine_name())


def run_claim(files: Iterable[str | Path], claim_id: str | None = None, source: str = "upload",
              engine: str | None = None) -> dict:
    """Run the full multi-agent pipeline on a set of claim documents and return the report dict."""
    eng = engine or engine_name()
    state: ClaimState = {"input_files": [str(f) for f in files], "source": source}
    if claim_id:
        state["claim_id"] = claim_id
    final = get_workflow(eng).invoke(state, {"recursion_limit": 50})
    report = final["report"]
    report["engine"] = eng
    report["agent_trace"] = final.get("trace", [])  # includes the report agent itself
    report["errors"] = final.get("errors", [])
    return report


def mermaid() -> str:
    """Mermaid diagram of the workflow (used by the UI and docs)."""
    lines = ["flowchart TD", "  START([Start]) --> intake"]
    label = {k: AGENT_REGISTRY.get(k, {}).get("name", k) for k in NODES}
    for k in NODES:
        lines.append(f'  {k}["{label[k]}"]')
    for a, b in EDGES:
        if a == "START":
            continue
        lines.append(f"  {a} --> {'END([End])' if b == 'END' else b}")
    for sources, target in JOINS:
        for s in sources:
            lines.append(f"  {s} --> {target}")
    lines.append("  validate -- complete --> knowledge")
    lines.append("  validate -- missing docs --> request_docs")
    lines.append("  decision -- HIGH risk --> siu")
    lines.append("  decision -- LOW / MEDIUM --> settlement")
    return "\n".join(lines)
