"""FastAPI application: REST API + web UI for ClaimGuard AI.

Run locally:   uvicorn app.api:app --reload      (then open http://127.0.0.1:8000)
API docs:      http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.agents.base import AGENT_REGISTRY, CATEGORIES
from app.config import (APP_NAME, APP_VERSION, LOW_RISK_MAX, MEDIUM_RISK_MAX, ML_WEIGHT, RULE_WEIGHT, SAMPLES_DIR,
                        UPLOADS_DIR, APP_DIR)
from app.graph import NODES, engine_name, mermaid, run_claim
from app.ml.model import load_model
from app.report_html import render_report_html
from app.tools.document_reader import SUPPORTED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
WEB_DIR = APP_DIR / "web"
MAX_FILES, MAX_BYTES = 10, 10 * 1024 * 1024

@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_model()  # trains automatically on first boot if the artifact is missing
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan,
              description="Agentic AI system that validates medical insurance claim documents and detects fraud "
                          "(LangGraph multi-agent workflow + rule engine + ML scoring).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


def _samples() -> list[dict]:
    idx = SAMPLES_DIR / "index.json"
    return json.loads(idx.read_text()) if idx.exists() else []


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:120]


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "engine": engine_name(),
            "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/samples")
def samples() -> list[dict]:
    return _samples()


@app.get("/api/samples/{claim_id}/files/{filename}")
def sample_file(claim_id: str, filename: str):
    path = (SAMPLES_DIR / _safe(claim_id) / _safe(filename)).resolve()
    if not str(path).startswith(str(SAMPLES_DIR.resolve())) or not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="application/pdf" if path.suffix == ".pdf" else None)


@app.post("/api/samples/{claim_id}/run")
def run_sample(claim_id: str) -> dict:
    folder = SAMPLES_DIR / _safe(claim_id)
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in SUPPORTED and p.name != "scenario.json")
    if not files:
        raise HTTPException(404, f"Sample claim {claim_id} not found")
    return run_claim(files, claim_id=claim_id, source="sample")


@app.post("/api/claims/upload")
async def upload_claim(files: List[UploadFile] = File(...)) -> dict:
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload between 1 and {MAX_FILES} documents")
    batch = UPLOADS_DIR / f"UPL-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    batch.mkdir(parents=True)
    saved = []
    for f in files:
        name = _safe(f.filename or "document")
        if Path(name).suffix.lower() not in SUPPORTED:
            shutil.rmtree(batch, ignore_errors=True)
            raise HTTPException(415, f"{name}: unsupported type. Allowed: {', '.join(sorted(SUPPORTED))}")
        data = await f.read()
        if len(data) > MAX_BYTES:
            shutil.rmtree(batch, ignore_errors=True)
            raise HTTPException(413, f"{name} is larger than 10 MB")
        (batch / name).write_bytes(data)
        saved.append(batch / name)
    return run_claim(saved, source="upload")


@app.get("/api/claims")
def list_claims(limit: int = 100) -> dict:
    return {"runs": db.list_runs(limit), "stats": db.stats()}


@app.get("/api/claims/{run_id}")
def get_claim(run_id: str) -> dict:
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@app.get("/api/claims/{run_id}/report", response_class=HTMLResponse)
def claim_report(run_id: str) -> HTMLResponse:
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return HTMLResponse(render_report_html(r))


@app.get("/api/workflow")
def workflow() -> dict:
    return {
        "engine": engine_name(), "mermaid": mermaid(),
        "agents": [{"node": k, **AGENT_REGISTRY[k]} for k in NODES],
        "categories": CATEGORIES,
        "scoring": {"rule_weight": RULE_WEIGHT, "ml_weight": ML_WEIGHT, "low_max": LOW_RISK_MAX, "medium_max": MEDIUM_RISK_MAX},
    }


@app.get("/api/model")
def model_info() -> JSONResponse:
    return JSONResponse(load_model()["metrics"])
