"""Central configuration for ClaimGuard AI.

Every threshold can be overridden with an environment variable (or a .env file),
so business users can tune the system without touching code.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
KNOWLEDGE_DIR = APP_DIR / "knowledge"
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "sample_claims"
UPLOADS_DIR = DATA_DIR / "uploads"
TRAINING_DIR = DATA_DIR / "training"
OUTPUTS_DIR = BASE_DIR / "outputs"
MODEL_DIR = APP_DIR / "ml" / "artifacts"
DB_PATH = Path(os.getenv("CLAIMGUARD_DB", DATA_DIR / "claimguard.db"))

for _d in (UPLOADS_DIR, TRAINING_DIR, OUTPUTS_DIR, MODEL_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


# ---- Fraud score bands (0-100) ------------------------------------------------
LOW_RISK_MAX = _f("LOW_RISK_MAX", 30)        # score < 30  -> Genuine / auto-approve
MEDIUM_RISK_MAX = _f("MEDIUM_RISK_MAX", 65)  # 30-65       -> Suspicious / human review
#                                              score > 65  -> High risk / SIU

# ---- Score blending ------------------------------------------------------------
RULE_WEIGHT = _f("RULE_WEIGHT", 0.55)
ML_WEIGHT = _f("ML_WEIGHT", 0.45)
CRITICAL_FLOOR = _f("CRITICAL_FLOOR", 70)   # min final score when a CRITICAL rule fires

# ---- Business rules ------------------------------------------------------------
INITIAL_WAITING_DAYS = int(_f("INITIAL_WAITING_DAYS", 30))     # IRDAI standard
PED_WAITING_MONTHS = int(_f("PED_WAITING_MONTHS", 36))         # IRDAI max (2024)
EARLY_CLAIM_DAYS = int(_f("EARLY_CLAIM_DAYS", 90))
CLAIM_SUBMISSION_DAYS = int(_f("CLAIM_SUBMISSION_DAYS", 30))
FREQUENT_CLAIMS_WINDOW_DAYS = int(_f("FREQUENT_CLAIMS_WINDOW_DAYS", 365))
FREQUENT_CLAIMS_THRESHOLD = int(_f("FREQUENT_CLAIMS_THRESHOLD", 2))
ITEM_TOLERANCE = _f("ITEM_TOLERANCE", 1.25)   # allowed headroom over benchmark rate

# ---- Optional LLM narrative (disabled by default) ---------------------------------
# Only Anthropic Claude is supported. The system is fully functional without it.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

APP_NAME = "ClaimGuard AI"
APP_VERSION = "1.0.0"
