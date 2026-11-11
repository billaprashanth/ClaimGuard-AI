@echo off
REM One-command local setup + run (Windows)
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -q -r requirements.txt
python -m app.cli showcase
echo Open http://127.0.0.1:8000
uvicorn app.api:app --host 127.0.0.1 --port 8000
