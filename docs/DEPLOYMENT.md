# Deployment guide: hosting ClaimGuard AI live

You have two complementary ways to put the project online:

| Option | What is live | Cost | Effort |
|---|---|---|---|
| **A. Render (recommended)** | The full app: upload documents, agents run, REST API, Swagger | Free plan | ~10 min |
| **B. GitHub Pages** | `outputs/showcase.html`: the UI with all 7 precomputed results, no backend | Free | ~3 min |
| C. Any Docker host | Full app | varies | ~10 min |

---

## A. Render (full live app)

1. **Push the project to GitHub**
   ```bash
   cd ClaimGuard-AI
   git init && git add . && git commit -m "ClaimGuard AI: agentic claim fraud detection"
   git branch -M main
   git remote add origin https://github.com/<your-user>/Agentic-AI-InsuranceClaim.git
   git push -u origin main --force      # --force only if you are replacing the old project
   ```
   `.gitignore` already excludes `.env`, `.venv/`, the local database and uploads. Never commit API keys.

2. **Create the service**: sign in at <https://render.com>, then *New > Blueprint*, and pick the repository. Render reads `render.yaml` and builds the `Dockerfile` on the **free** plan. The model is trained during the build, so the first request is fast.

3. **Open the URL** Render shows (e.g. `https://claimguard-ai.onrender.com`). Check `https://<your-app>.onrender.com/api/health` and `/docs`.

Things to know about the free plan:
- The service **sleeps after 15 minutes without traffic**. The first request after that takes roughly a minute while it wakes. Open the URL a minute before a demo.
- The filesystem is **ephemeral**. The SQLite claims register resets on every restart or redeploy. That is fine for a demo; use a managed Postgres for production.
- 512 MB RAM is enough for this app.

Without the Blueprint: *New > Web Service*, connect the repo, Runtime **Docker**, Health check path `/api/health`.
Without Docker: Runtime **Python 3**, Build `pip install -r requirements.txt`, Start `uvicorn app.api:app --host 0.0.0.0 --port $PORT`.

## B. GitHub Pages (static showcase)

1. Run `python -m app.cli showcase` (already done; `outputs/showcase.html` is in the zip).
2. Copy it to `docs/index.html` in your repo (or keep it in `outputs/` and point Pages there).
3. GitHub repo, then *Settings > Pages > Deploy from a branch > main / docs*.
4. Live at `https://<your-user>.github.io/<repo>/`.

The page is fully self-contained. It includes the sample PDFs, results, reports and model metrics, and works offline.

## C. Docker anywhere (Railway, Fly.io, Azure, AWS, a VM)

```bash
docker build -t claimguard-ai .
docker run -p 8000:8000 claimguard-ai
# open http://localhost:8000
```
The container honours the `PORT` environment variable.

## Environment variables

See `.env.example`. None are required. The useful ones:

| Variable | Default | Meaning |
|---|---|---|
| `LOW_RISK_MAX` / `MEDIUM_RISK_MAX` | 30 / 65 | Band thresholds |
| `RULE_WEIGHT` / `ML_WEIGHT` | 0.55 / 0.45 | Score blend |
| `CLAIMGUARD_ENGINE` | `langgraph` | `builtin` to run without LangGraph |
| `LLM_PROVIDER` | `none` | `anthropic` to let Claude write the case note (needs `ANTHROPIC_API_KEY`) |
| `CLAIMGUARD_DB` | `data/claimguard.db` | SQLite path |

## Security note for the old repository

The previous version of this repo committed a `.env` file containing a Groq API key, plus the whole `.venv/`. Revoke that key in the Groq console. Rewriting the repo will not un-leak it, because it stays in Git history. Push this project with the provided `.gitignore`.
