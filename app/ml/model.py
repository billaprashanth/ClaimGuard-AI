"""ML fraud-scoring model: synthetic historical dataset, training, evaluation and inference.

* GradientBoostingClassifier  -> calibrated-ish fraud probability (0-1)
* IsolationForest (on genuine claims only) -> anomaly score (0-100)

The dataset is SYNTHETIC but generated from three realistic behavioural profiles
(genuine, soft fraud / bill inflation, hard fraud). Replace data/training/historical_claims.csv
with your own labelled claims and run `python -m app.cli train` to retrain.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from app.config import MODEL_DIR, TRAINING_DIR

FEATURES = [
    "bill_ratio", "max_item_ratio", "room_rent_ratio", "duplicate_items", "los_ratio",
    "unrelated_item_count", "opd_manageable", "dx_mismatch", "hospital_risk", "hospital_network",
    "hospital_small_clinic", "days_since_inception_log", "undeclared_ped", "prior_claims_12m",
    "registry_duplicate", "doc_issue_count", "claim_amount_log", "is_reimbursement", "patient_age",
]
FEATURE_LABELS = {
    "bill_ratio": "Bill vs typical cost", "max_item_ratio": "Highest item vs tariff", "room_rent_ratio": "Room rent vs benchmark",
    "duplicate_items": "Duplicate line items", "los_ratio": "Length of stay vs typical", "unrelated_item_count": "Clinically unrelated items",
    "opd_manageable": "OPD-manageable condition admitted", "dx_mismatch": "Diagnosis inconsistency", "hospital_risk": "Provider risk index",
    "hospital_network": "Network hospital", "hospital_small_clinic": "Small clinic", "days_since_inception_log": "Policy age",
    "undeclared_ped": "Undeclared pre-existing disease", "prior_claims_12m": "Claims in last 12 months",
    "registry_duplicate": "Duplicate in industry registry", "doc_issue_count": "Document issues",
    "claim_amount_log": "Claim amount", "is_reimbursement": "Reimbursement claim", "patient_age": "Patient age",
}
MODEL_PATH = MODEL_DIR / "fraud_model.joblib"
METRICS_PATH = MODEL_DIR / "model_metrics.json"
DATA_PATH = TRAINING_DIR / "historical_claims.csv"
MODEL_VERSION = "gbm-v1"


# --------------------------------------------------------------------------- dataset
def generate_dataset(n: int = 8000, seed: int = 42) -> pd.DataFrame:
    """Four behavioural profiles with deliberately OVERLAPPING distributions (no single feature
    separates fraud from genuine - just like real claims data)."""
    rng = np.random.default_rng(seed)
    names = ["genuine", "inflation", "phantom", "misrepresentation"]
    profile = rng.choice(names, size=n, p=[0.80, 0.10, 0.05, 0.05])
    P = {  # per-profile parameters
        #               bill(mu,sd)  item(mu,sd)  room(mu,sd)  los(mu,sd)  unrel  risk(a,b) days(lo,hi) ped   reg   docs prior dup  opd  dxm  net  small reimb amt
        "genuine":      ((0.58, .45), (0.70, .35), (0.75, .30), (0.70, .35), .06, (2, 12), (30, 3000), .02, .003, .5, .35, .02, .10, .01, .75, .08, .40, 1.0),
        "inflation":    ((1.60, .35), (1.35, .35), (1.25, .30), (1.15, .35), .6, (3, 6), (20, 1200), .04, .01, 1.0, 1.0, .25, .30, .05, .40, .30, .80, 1.6),
        "phantom":      ((2.00, .45), (1.50, .40), (1.30, .35), (1.00, .50), 1.5, (5, 4), (5, 400), .08, .05, 2.0, 1.5, .35, .45, .20, .20, .50, .90, 2.0),
        "misrepresentation": ((0.70, .40), (0.80, .30), (0.80, .30), (0.80, .35), .1, (2, 10), (5, 300), .45, .30, 1.5, .6, .05, .10, .05, .55, .10, .60, 1.4),
    }
    ln = lambda m, sd: float(np.exp(rng.normal(np.log(m), sd)))  # noqa: E731
    rows = []
    for p in profile:
        (bm, bs), (im, isd), (rm, rsd), (lm, lsd), unrel, (ra, rb), (dlo, dhi), ped, reg, docs, prior, dup, opd, dxm, net, small, reimb, amt = P[p]
        days = float(np.exp(rng.uniform(np.log(dlo), np.log(dhi))))
        if p == "genuine" and rng.random() < 0.06:
            days = rng.uniform(5, 90)
        rows.append({
            "bill_ratio": ln(bm, bs), "max_item_ratio": ln(im, isd), "room_rent_ratio": ln(rm, rsd),
            "duplicate_items": int(rng.random() < dup), "los_ratio": ln(lm, lsd),
            "unrelated_item_count": int(rng.poisson(unrel)), "opd_manageable": int(rng.random() < opd),
            "dx_mismatch": int(rng.random() < dxm), "hospital_risk": float(rng.beta(ra, rb)),
            "hospital_network": int(rng.random() < net), "hospital_small_clinic": int(rng.random() < small),
            "days_since_inception_log": math.log1p(days), "undeclared_ped": int(rng.random() < ped),
            "prior_claims_12m": int(rng.poisson(prior)), "registry_duplicate": int(rng.random() < reg),
            "doc_issue_count": int(rng.poisson(docs)),
            "claim_amount_log": math.log1p(float(np.exp(rng.normal(10.9, 0.7))) * amt),
            "is_reimbursement": int(rng.random() < reimb), "patient_age": int(rng.uniform(18, 80)),
            "profile": p,
        })
    df = pd.DataFrame(rows)
    noise = rng.random(n)
    df["is_fraud"] = np.where(df["profile"] == "genuine", (noise < 0.03).astype(int), (noise > 0.08).astype(int))
    return df


# --------------------------------------------------------------------------- training
def train(save: bool = True, data_path: Path | None = None) -> dict:
    path = data_path or DATA_PATH
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = generate_dataset()
        df.to_csv(path, index=False)
    X, y = df[FEATURES].astype(float), df["is_fraud"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=7)
    clf = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.05, subsample=0.9, random_state=7)
    clf.fit(Xtr, ytr)
    proba = clf.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    genuine = X[y == 0]
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=7).fit(genuine)
    raw = -iso.score_samples(genuine)
    lo, hi = float(np.percentile(raw, 50)), float(np.percentile(raw, 99.5))

    metrics = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "rows": int(len(df)), "fraud_rate": round(float(y.mean()), 4),
        "test_rows": int(len(yte)),
        "roc_auc": round(float(roc_auc_score(yte, proba)), 4),
        "pr_auc": round(float(average_precision_score(yte, proba)), 4),
        "precision@0.5": round(float(precision_score(yte, pred)), 4),
        "recall@0.5": round(float(recall_score(yte, pred)), 4),
        "f1@0.5": round(float(f1_score(yte, pred)), 4),
        "confusion_matrix@0.5": confusion_matrix(yte, pred).tolist(),
        "feature_importance": dict(sorted(((f, round(float(i), 4)) for f, i in zip(FEATURES, clf.feature_importances_)),
                                          key=lambda kv: -kv[1])),
    }
    bundle = {
        "model": clf, "iso": iso, "iso_range": (lo, hi), "features": FEATURES,
        "genuine_median": genuine.median().to_dict(),
        "genuine_iqr": (genuine.quantile(0.75) - genuine.quantile(0.25)).replace(0, 1).to_dict(),
        "metrics": metrics,
    }
    if save:
        joblib.dump(bundle, MODEL_PATH)
        METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    load_model.cache_clear()
    return metrics


@lru_cache(maxsize=1)
def load_model() -> dict:
    try:
        bundle = joblib.load(MODEL_PATH)
        if bundle["metrics"].get("sklearn_version") != sklearn.__version__:
            raise ValueError("model trained with a different scikit-learn version")
        return bundle
    except Exception:
        train(save=True)  # self-healing: (re)train in ~5 seconds
        return joblib.load(MODEL_PATH)


# --------------------------------------------------------------------------- inference
def score(features: dict) -> dict:
    b = load_model()
    row = pd.DataFrame([[float(features.get(f, b["genuine_median"].get(f, 0)) or 0) for f in FEATURES]], columns=FEATURES)
    prob = float(b["model"].predict_proba(row)[0, 1])
    raw = float(-b["iso"].score_samples(row)[0])
    lo, hi = b["iso_range"]
    anomaly = max(0.0, min(100.0, (raw - lo) / max(hi - lo, 1e-9) * 100))
    imp = b["metrics"]["feature_importance"]
    drivers = []
    for f in FEATURES:
        z = (row[f].iloc[0] - b["genuine_median"][f]) / (b["genuine_iqr"][f] or 1)
        if f in ("hospital_network", "days_since_inception_log"):
            z = -z  # being in-network / an older policy lowers risk
        contrib = imp.get(f, 0) * z
        if contrib > 0.02:
            drivers.append({"feature": f, "label": FEATURE_LABELS[f], "value": round(float(row[f].iloc[0]), 3),
                            "weight": round(float(contrib), 3)})
    drivers.sort(key=lambda d: -d["weight"])
    if prob < 0.15:
        drivers = []  # nothing worth explaining for a clearly genuine claim
    return {
        "fraud_probability": round(prob, 4),
        "ml_score": round(prob * 100, 1),
        "anomaly_score": round(anomaly, 1),
        "top_drivers": drivers[:5],
        "features": {f: round(float(row[f].iloc[0]), 4) for f in FEATURES},
        "model_version": MODEL_VERSION,
        "model_metrics": {k: b["metrics"][k] for k in ("roc_auc", "pr_auc", "precision@0.5", "recall@0.5", "rows")},
    }
