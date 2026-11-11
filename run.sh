#!/usr/bin/env bash
# One-command local setup + run (macOS / Linux)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python -m app.cli showcase
echo "Open http://127.0.0.1:8000"
uvicorn app.api:app --host 127.0.0.1 --port 8000
