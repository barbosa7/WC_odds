"""Train and persist the match-outcome model."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.constants import RESULT_MAP
from ml.features import FEATURE_COLS, FeatureEngine

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "wc_data"
MODEL_PATH = DATA_DIR / "ml_match_model.joblib"
META_PATH = DATA_DIR / "ml_match_model.json"

TRAIN_CANDIDATES = [
    DATA_DIR / "kaggle_train.csv",
    Path.home() / "Downloads/wc2026-ai-prediction/train.csv",
    ROOT.parent / "Downloads/wc2026-ai-prediction/train.csv",
]


def resolve_train_path() -> Path:
    for p in TRAIN_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Kaggle train.csv not found. Copy to wc_data/kaggle_train.csv "
        "or keep at ~/Downloads/wc2026-ai-prediction/train.csv"
    )


def build_training_matrix(train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, FeatureEngine, np.ndarray]:
    train = train.sort_values("date").reset_index(drop=True)
    engine = FeatureEngine()
    rows: list[dict] = []
    labels: list[int] = []
    weights: list[float] = []

    for _, m in train.iterrows():
        neutral = str(m["neutral"]).lower() in ("true", "1", "t")
        feats = engine.extract(
            m["home_team"],
            m["away_team"],
            m["date"],
            neutral=neutral,
            tournament=m["tournament"],
            home_conf=m.get("home_conf", ""),
            away_conf=m.get("away_conf", ""),
        )
        rows.append(feats)
        labels.append(RESULT_MAP[m["result"]])
        weights.append(2.5 if m["tournament"] == "FIFA World Cup" else 1.0)
        engine.update(
            m["home_team"],
            m["away_team"],
            m["date"],
            m["result"],
            float(m["home_score"]),
            float(m["away_score"]),
            neutral=neutral,
            tournament=m["tournament"],
        )

    X = np.array([[r[c] for c in FEATURE_COLS] for r in rows], dtype=float)
    return X, np.array(labels), engine, np.array(weights, dtype=float)


def fit_model(X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> Pipeline:
    pipe = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, C=0.8)),
        ]
    )
    pipe.fit(X, y, clf__sample_weight=sample_weight)
    return pipe


def train_and_save(train_path: Path | None = None, alpha: float = 0.9) -> dict:
    path = train_path or resolve_train_path()
    train = pd.read_csv(path)
    train["date"] = pd.to_datetime(train["date"])

    X, y, engine, sw = build_training_matrix(train)
    model = fit_model(X, y, sw)

    payload = {
        "model": model,
        "base_engine": engine,
        "alpha": alpha,
        "feature_cols": FEATURE_COLS,
        "train_path": str(path),
        "train_rows": len(train),
    }
    DATA_DIR.mkdir(exist_ok=True)
    joblib.dump(payload, MODEL_PATH)

    meta = {
        "alpha": alpha,
        "train_path": str(path),
        "train_rows": len(train),
        "features": len(FEATURE_COLS),
    }
    META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


def clone_engine(engine: FeatureEngine) -> FeatureEngine:
    eng = FeatureEngine()
    eng.teams = copy.deepcopy(engine.teams)
    eng.h2h = copy.deepcopy(engine.h2h)
    return eng
