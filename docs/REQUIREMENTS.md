# ClaimGuard AI: Software Requirements Specification

Version 1.0, November 2026

## 1. Purpose

Build an agentic AI system that **processes medical insurance claims, validates the claim documents and identifies fraudulent claims**, then hosts it as a live web application with a showcase of prepared inputs and outputs.

### 1.1 Brief (as given)

1. Any insurance type. **Chosen: medical / health insurance (India).**
2. Input documents can be collected online, on any domain. **Delivered:** 7 realistic claim packages (25 PDFs) modelled on Indian hospital and insurer formats, plus a structured JSON example. Regulatory rules come from public IRDAI guidance.
3. High-level use of an agentic AI framework (LangChain or LangGraph). **Chosen: LangGraph `StateGraph`.**
4. If it takes time to run, prepare inputs, run once, keep outputs ready and showcase input and output. **Delivered:** `outputs/` + `outputs/showcase.html` + `outputs/SHOWCASE.md`.

### 1.2 Constraints: technologies that must NOT be used

LangChain, Groq, Grok, OpenAI, GPT, LLaMA, HuggingFace, any vector DB (Pinecone, Chroma, FAISS), Redis.

Compliance: none of these are imported or required. Knowledge retrieval uses plain JSON knowledge bases with deterministic lookups. Persistence uses SQLite (standard library). `langgraph` installs `langchain-core` as a transitive package. The code never imports it, and `CLAIMGUARD_ENGINE=builtin` removes even that dependency (see README).

## 2. Users

| User | Needs |
|---|---|
| Claims assessor | Fast, explainable verdict per claim; settlement computation |
| Medical officer / reviewer | Medium-risk queue with reasons and evidence |
| SIU investigator | High-risk cases with a prioritised investigation plan |
| Policyholder (indirect) | Clear deficiency letter when documents are missing |
| Evaluator / demo audience | Showcase of inputs and outputs, live hosted app |

## 3. Functional requirements

| ID | Requirement | Implemented in |
|---|---|---|
| FR-1 | Accept claim documents as PDF, TXT, JSON (and PNG/JPG with optional OCR), via web upload, REST API and CLI | `api.py`, `cli.py`, `tools/document_reader.py` |
| FR-2 | Classify each document (claim form, hospital bill, discharge summary, prescription, lab report) | Document Classifier Agent |
| FR-3 | Extract structured fields and itemised bill line items; build one consolidated claim | Data Extraction Agent, `tools/extractor.py` |
| FR-4 | Validate documents: mandatory documents and fields, bill arithmetic, claimed vs billed, hospital seal and signature, doctor registration number, hospital registration number, cross-document consistency of name and dates, submission timeliness, **PDF tampering forensics** | Document Validation Agent |
| FR-5 | Detect fraud across 9 categories (section 4) with explainable reasons | Policy, Medical, Billing, Provider, History agents |
| FR-6 | Compute an ML fraud probability and anomaly score | ML Risk Scoring Agent |
| FR-7 | Produce a fraud score 0-100, a risk band and a routing decision | Fraud Risk Decision Agent |
| FR-8 | Output exactly: Fraud Score, Suspicious Reasons, Triggered Categories | Report Agent (`output_text`) |
| FR-9 | Pause incomplete claims and draft a document request | Document Request Agent |
| FR-10 | Compute settlement: non-payables, room-rent proportionate deduction, ICU cap, co-pay, sum insured | Settlement Agent |
| FR-11 | Create an SIU case for high-risk claims: priority, due date, task list, evidence, payment hold | SIU Investigation Agent |
| FR-12 | Persist every run (audit trail) and list or retrieve past runs | `db.py`, `/api/claims` |
| FR-13 | Web UI: pick a sample or upload, see verdict, reasons, agent timeline, outcome, checks, bill; claims register; workflow; model page | `app/web/` |
| FR-14 | Printable HTML report per claim | `report_html.py` |
| FR-15 | Batch showcase: run all samples once and store outputs | `showcase.py` |
| FR-16 | Configurable thresholds and weights without code changes | `config.py`, `.env` |

## 4. Fraud rule catalogue

Severity points: LOW 10, MEDIUM 22, HIGH 40, CRITICAL 75.

| Category | Rule (code) | Severity |
|---|---|---|
| **Bill Amount** | Total bill > 1.3x typical max for diagnosis at hospital tier (`BILL_HIGH`); > 2x | MEDIUM / HIGH |
| **Single Item Charge** | Item rate > tariff benchmark x tier x 1.25 (`ITEM_OVERPRICED`) | MEDIUM / HIGH |
| | Single non-procedure item > 40% of bill (`ITEM_DOMINANT`) | MEDIUM |
| **Diagnosis Mismatch** | Claim-form diagnosis differs from discharge summary (`DX_FORM_MISMATCH`) | HIGH |
| | ICD-10 code inconsistent with diagnosis text (`ICD_MISMATCH`) | MEDIUM |
| | Clinically unrelated or high-cost items for the diagnosis, e.g. MRI for fever (`UNRELATED_TREATMENT`) | MEDIUM / HIGH |
| | Diagnosis not in clinical KB (`DX_UNKNOWN`) | LOW |
| **Hospital Pattern Risk** | Blacklisted (`HOSP_BLACKLISTED`) | CRITICAL |
| | Fraud watchlist (`HOSP_WATCHLIST`); provider risk index >= 0.3 (`HOSP_RISKY`) | HIGH / MEDIUM |
| | Claims >= 1.8x 90-day baseline (`HOSP_SPIKE`) | MEDIUM |
| | Small clinic billing like a premium hospital or advanced diagnostics (`SMALL_CLINIC_PREMIUM`) | HIGH |
| | Not in registry (`HOSP_UNKNOWN`); registration number mismatch (`HOSP_REG_MISMATCH`) | MEDIUM / HIGH |
| | Non-network reimbursement (`NON_NETWORK`) | LOW |
| **Patient Claim History** | >= 2 claims in 12 months (`FREQUENT_CLAIMS`), >= 3 | MEDIUM / HIGH |
| | Same high-cost procedure repeated (`REPEAT_PROCEDURE`) | MEDIUM |
| | Same bill already claimed elsewhere (`DUPLICATE_CLAIM`) | CRITICAL |
| | Other policy found but declared "None" (`UNDISCLOSED_POLICY`) | HIGH |
| **Document Issues** | Missing mandatory document (`DOC_MISSING`) | MEDIUM (blocking) |
| | Bill does not tally (`BILL_NOT_TALLY`); claimed > billed (`CLAIM_EXCEEDS_BILL`) | HIGH |
| | No seal or signature (`BILL_NO_SEAL`, `DS_NO_SEAL`); no doctor reg. no (`NO_DOCTOR_REG`) | MEDIUM |
| | Name or date mismatch across documents; discharge before admission | HIGH |
| | PDF edited with image software or modified after issue (`DOC_TAMPERED`) | CRITICAL |
| | Policy not found / patient not insured (`POLICY_NOT_FOUND`, `NOT_INSURED_MEMBER`) | CRITICAL |
| | DOB mismatch with policy (`DOB_MISMATCH`) | HIGH |
| | Submitted > 30 days after discharge (`LATE_SUBMISSION`) | LOW |
| **Treatment Duration Abnormality** | LOS > typical max (`LONG_STAY`); > 1.6x | MEDIUM / HIGH |
| | In-patient claim for OPD-manageable condition (`OPD_AS_IPD`) | MEDIUM |
| | Kept >= 3 days after documented recovery (`POST_RECOVERY_STAY`) | MEDIUM |
| | < 24 h admission for non-daycare (`SHORT_STAY`) | MEDIUM |
| **Room Rent / Procedure Overcharging** | Room rate > tier benchmark (`ROOM_OVERCHARGE`) | MEDIUM / HIGH |
| | Room-days billed > stay + 1 (`ROOM_DAYS`); duplicate line items (`DUPLICATE_ITEM`) | MEDIUM |
| **Suspicious Timing (new policy)** | Illness claim inside 30-day initial waiting period (`INITIAL_WAITING`) | HIGH + not admissible |
| | Claim within 90 days (`EARLY_CLAIM`) / first year (`FIRST_YEAR_CLAIM`) | MEDIUM / LOW |
| | Specific-disease waiting period, e.g. hernia, cataract 24 months (`SPECIFIC_WAITING`) | MEDIUM + not admissible |
| | Claim soon after sum-insured enhancement (`SI_ENHANCED`) | MEDIUM |
| | Undeclared pre-existing condition found in clinical history (`UNDECLARED_PED`) | HIGH |

## 5. Decision logic

```
fraud_score = 0.55 x rule_score + 0.45 x ml_score   (CRITICAL finding -> >= 70)
< 30   -> AUTO_APPROVE, or NOT_ADMISSIBLE if policy coverage fails
30-65  -> HUMAN_REVIEW (provisional settlement)
> 65   -> SIU_INVESTIGATION (payment hold)
blocking validation failure -> PENDING_DOCUMENTS (not scored)
```

## 6. Non-functional requirements

| ID | Requirement | How it is met |
|---|---|---|
| NFR-1 Explainability | Every point of score traces to a named rule, agent and evidence | Findings carry code, category, severity, reason, evidence, agent |
| NFR-2 Performance | < 2 s per claim on a laptop | ~0.2-0.4 s per claim (PDF parsing dominates) |
| NFR-3 Robustness | One failing agent must not stop the pipeline | `@agent` decorator isolates exceptions into `errors` |
| NFR-4 Offline | Runs with no external API | No API keys required; LLM optional |
| NFR-5 Security | Safe uploads | Extension allow-list, 10 MB / 10 files limit, filename sanitising, path-traversal guard, no secrets in repo |
| NFR-6 Portability | Linux / macOS / Windows, Docker | `requirements.txt`, `Dockerfile`, `run.sh`, `run.bat` |
| NFR-7 Testability | Automated tests | 26 pytest tests incl. both graph engines and the API |
| NFR-8 Auditability | Every decision stored | SQLite `claim_runs` with full JSON |
| NFR-9 Accessibility | Usable UI | Keyboard focus styles, reduced-motion support, responsive to 390 px |

## 7. Data

| File | Content |
|---|---|
| `app/knowledge/medical_kb.json` | 12 diagnoses: ICD-10, care level, LOS, cost band, expected and unrelated items, specific waiting periods; PED markers |
| `app/knowledge/tariff_benchmarks.json` | Item rate caps, room rents, tier multipliers, non-payable items |
| `app/knowledge/hospitals.json` | 7 fictional providers with tier, network, risk index, watchlist / blacklist, claim volumes |
| `app/knowledge/policies.json` | 7 fictional policies with members, sum insured, caps, co-pay, declared PEDs |
| `app/knowledge/claims_history.json` | Past claims per policy and a simulated industry registry |
| `data/training/historical_claims.csv` | 8,000 synthetic labelled claims for the ML model |

## 8. Acceptance criteria (all met)

- [x] 7 sample claim packages produce the intended outcomes (tested in `tests/test_pipeline.py`)
- [x] Output contains fraud score, suspicious reasons and triggered categories
- [x] LangGraph workflow with parallel agents, join and conditional routing
- [x] No prohibited technology used
- [x] Web app with upload, results, register, workflow and model pages; REST API with Swagger
- [x] Precomputed outputs and an offline showcase page
- [x] Deployable to a free host (Render Blueprint + Dockerfile)

## 9. Future scope

Real OCR for handwritten bills; ICD-10/PCS full code sets; insurer tariff and package-rate integration; network graph analytics on doctor-hospital-claimant links; reviewer feedback loop to retrain the model; role-based access and PII encryption at rest.
