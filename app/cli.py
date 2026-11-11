"""Command-line interface.

  python -m app.cli samples                 # (re)generate the 7 sample claim PDFs
  python -m app.cli train                   # (re)train the ML model
  python -m app.cli run data/sample_claims/CLM-2026-1004
  python -m app.cli run claim_form.pdf hospital_bill.pdf discharge_summary.pdf --json out.json
  python -m app.cli showcase                # run all samples, write outputs/
  python -m app.cli graph                   # print the Mermaid workflow diagram
  python -m app.cli serve --port 8000       # start the web app
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from app.config import BASE_DIR


def _files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in {".pdf", ".txt", ".json", ".md", ".png", ".jpg", ".jpeg"}
                          and x.name not in ("scenario.json", "index.json"))
        else:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="claimguard", description="ClaimGuard AI - agentic claim validation & fraud detection")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("samples", help="generate sample claim documents")
    sub.add_parser("train", help="train / retrain the ML fraud model")
    r = sub.add_parser("run", help="process a claim folder or a list of documents")
    r.add_argument("paths", nargs="+")
    r.add_argument("--json", help="write the full result JSON to this file")
    r.add_argument("--engine", choices=["langgraph", "builtin"])
    sub.add_parser("showcase", help="run all sample claims and write outputs/")
    sub.add_parser("graph", help="print Mermaid diagram of the workflow")
    s = sub.add_parser("serve", help="run the web application")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.cmd == "samples":
        return subprocess.call([sys.executable, str(BASE_DIR / "scripts" / "generate_sample_claims.py")])
    if a.cmd == "train":
        from app.ml.model import train
        m = train()
        print(json.dumps({k: v for k, v in m.items() if k != "feature_importance"}, indent=2))
        return 0
    if a.cmd == "run":
        from app.graph import run_claim
        files = _files(a.paths)
        res = run_claim(files, engine=a.engine)
        print(res["output_text"])
        print("\n" + res["narrative"])
        for t in res["agent_trace"]:
            print(f"  [{t['duration_ms']:>7.1f} ms] {t['agent']:<28} {t['summary']}")
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=2, default=str))
            print(f"\nSaved {a.json}")
        return 0
    if a.cmd == "showcase":
        from app.showcase import run_all
        print("Running all sample claims through the agent workflow...")
        run_all()
        print("Done. See outputs/SHOWCASE.md and open outputs/showcase.html in a browser.")
        return 0
    if a.cmd == "graph":
        from app.graph import mermaid
        print(mermaid())
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("app.api:app", host=a.host, port=a.port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
