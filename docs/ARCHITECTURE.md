# Architecture

## Why this is "agentic"

Each agent is an autonomous unit with its own goal, its own tools (document reader, extractor, knowledge-base lookups, ML model) and its own slice of the shared state. LangGraph coordinates them:

* **Shared state** (`app/state.py`, `ClaimState`): agents read the whole state and return partial updates. `findings`, `trace`, `errors` and `agent_outputs` use **reducers**, so parallel agents can write concurrently without clobbering each other.
* **Fan-out / fan-in**: after the Knowledge Retrieval Agent, five analyst agents run in the **same super-step** (in parallel). `add_edge([policy, medical, billing, provider, history], "ml_scoring")` makes the ML agent wait for all five.
* **Conditional routing**: `validate` routes to `request_docs` (blocking deficiencies) or `knowledge`. `decision` routes to `siu` (HIGH) or `settlement` (LOW / MEDIUM).
* **Fault isolation**: the `@agent` decorator (`app/agents/base.py`) times every agent, records a trace entry and converts exceptions into `errors` instead of crashing the claim.

## Layers

```
 Web UI (app/web)  ─┐
 REST API (FastAPI) ├─>  run_claim()  ─>  LangGraph StateGraph (app/graph.py)
 CLI (app/cli.py)  ─┘                         │
                                              ├── agents/      16 agents
                                              ├── tools/       reader, extractor, knowledge_base, utils
                                              ├── knowledge/   JSON knowledge bases
                                              ├── ml/          GradientBoosting + IsolationForest
                                              └── llm/         case-note writer (template / optional Claude)
                                       SQLite audit trail (app/db.py)
```

## Data flow for one claim

1. Files land in `data/uploads/<batch>/` (or a sample folder).
2. **classify**: `pdfplumber` text + `pypdf` metadata; keyword scoring decides the document type.
3. **extract**: label regexes (`Policy Number:`, `Date of Admission:`...) and a line-item regex (`S.No | Particulars | CATEGORY | Qty | Rate | Amount`) produce a consolidated claim; per-document values are kept in `cross_doc` for consistency checks.
4. **validate**: 12-16 checks; forensic flags (Photoshop/Canva/iLovePDF producer, ModDate > CreationDate + 1 day) become CRITICAL findings.
5. **knowledge**: deterministic lookups. Policy by number, member by fuzzy name, hospital by registration number then name, diagnosis by ICD-10 then longest alias. No embeddings and no vector DB: every match says *how* it matched.
6. **5 analysts in parallel** produce findings + features.
7. **ml_scoring** assembles 19 features, then outputs probability, anomaly and top drivers (importance x robust z-score).
8. **decision**: noisy-OR fusion, band, status, recommendation.
9. **settlement** or **siu**, then **report** (output text, narrative, DB save).

## Scoring maths

```
category_score(c) = 1 - Π_i (1 - p_i · 0.5^i / 100)       findings sorted by points, i = 0,1,2...
rule_score        = 1 - Π_c (1 - category_score(c)/100)
final             = 0.55 · rule_score + 0.45 · 100·P(fraud)
if any CRITICAL: final = max(final, 70 + 5·(n_critical-1) + 0.05·rule_score)
```

The within-category halving stops correlated signals (e.g. "long stay" and "kept after recovery") from double counting. Independent categories still compound.

## Two interchangeable engines

`app/graph.py` describes the workflow once (`NODES`, `EDGES`, `JOINS`, `CONDITIONALS`) and builds it with either `langgraph.graph.StateGraph` or `app.mini_graph.MiniStateGraph`. The mini engine implements the LangGraph semantics the project relies on: super-steps, reducers from `Annotated` hints, join edges and conditional path maps. `tests/test_pipeline.py::test_engines_agree` checks both engines produce identical scores.
