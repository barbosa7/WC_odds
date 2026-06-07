"""Train, evaluate, and persist the match-outcome model."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.constants import RESULT_MAP, norm_team, tournament_sample_weight
from ml.features import FEATURE_COLS, FeatureEngine

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "wc_data"
MODEL_PATH = DATA_DIR / "ml_match_model.joblib"
META_PATH = DATA_DIR / "ml_match_model.json"

WC_TOURNAMENT = "FIFA World Cup"
WC2018_START = pd.Timestamp("2018-06-14")
WC2022_START = pd.Timestamp("2022-11-20")


@dataclass
class TrainConfig:
    decay_lambda: float = 0.0
    alpha: float = 1.0
    wc_weight: float = 4.0
    major_weight: float = 2.0
    qual_weight: float = 1.0
    friendly_weight: float = 0.35
    other_weight: float = 0.75
    C: float = 0.8
    ref_date: pd.Timestamp | None = None
    min_train_date: pd.Timestamp | None = None
    skip_friendly_lr: bool = False


def log_loss_1x2(y_true: np.ndarray, proba: np.ndarray, eps: float = 1e-15) -> float:
    p = np.clip(proba, eps, 1 - eps)
    return float(-np.mean(np.log(p[np.arange(len(y_true)), y_true])))


def clone_engine(engine: FeatureEngine) -> FeatureEngine:
    eng = FeatureEngine()
    eng.teams = copy.deepcopy(engine.teams)
    eng.h2h = copy.deepcopy(engine.h2h)
    return eng


def warm_engine(train: pd.DataFrame, upto: pd.Timestamp | None = None) -> FeatureEngine:
    engine = FeatureEngine()
    df = train.sort_values("date")
    if upto is not None:
        df = df[df["date"] < upto]
    for _, m in df.iterrows():
        _update_row(engine, m)
    return engine


def _update_row(engine: FeatureEngine, m: pd.Series) -> None:
    neutral = str(m["neutral"]).lower() in ("true", "1", "t")
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


def _row_weight(m: pd.Series, cfg: TrainConfig) -> float:
    w = tournament_sample_weight(
        m["tournament"],
        wc_weight=cfg.wc_weight,
        major_weight=cfg.major_weight,
        qual_weight=cfg.qual_weight,
        friendly_weight=cfg.friendly_weight,
        other_weight=cfg.other_weight,
    )
    if cfg.decay_lambda > 0 and cfg.ref_date is not None:
        years_ago = max(0.0, (cfg.ref_date - m["date"]).days / 365.25)
        w *= math.exp(-cfg.decay_lambda * years_ago)
    return w


def build_training_matrix(
    train: pd.DataFrame,
    cfg: TrainConfig,
    *,
    warm: pd.DataFrame | None = None,
) -> tuple[np.ndarray, np.ndarray, FeatureEngine, np.ndarray]:
    train = train.sort_values("date").reset_index(drop=True)
    if cfg.ref_date is None and len(train):
        cfg = TrainConfig(
            decay_lambda=cfg.decay_lambda,
            alpha=cfg.alpha,
            wc_weight=cfg.wc_weight,
            major_weight=cfg.major_weight,
            qual_weight=cfg.qual_weight,
            friendly_weight=cfg.friendly_weight,
            other_weight=cfg.other_weight,
            C=cfg.C,
            ref_date=train["date"].max(),
            min_train_date=cfg.min_train_date,
        )

    engine = FeatureEngine()
    if warm is not None:
        for _, m in warm.sort_values("date").iterrows():
            if cfg.min_train_date is not None and m["date"] >= cfg.min_train_date:
                break
            _update_row(engine, m)

    rows: list[dict] = []
    labels: list[int] = []
    weights: list[float] = []

    for _, m in train.iterrows():
        if cfg.min_train_date is not None and m["date"] < cfg.min_train_date:
            _update_row(engine, m)
            continue
        is_friendly = str(m.get("tournament", "")) == "Friendly"
        if is_friendly and cfg.skip_friendly_lr:
            _update_row(engine, m)
            continue
        neutral = str(m["neutral"]).lower() in ("true", "1", "t")
        feats = engine.extract(
            m["home_team"],
            m["away_team"],
            m["date"],
            neutral=neutral,
            tournament=m["tournament"],
            home_conf=str(m.get("home_conf", "") or ""),
            away_conf=str(m.get("away_conf", "") or ""),
        )
        rows.append(feats)
        labels.append(RESULT_MAP[m["result"]])
        weights.append(_row_weight(m, cfg))
        _update_row(engine, m)

    X = np.array([[r[c] for c in FEATURE_COLS] for r in rows], dtype=float)
    return X, np.array(labels), engine, np.array(weights, dtype=float)


def fit_model(X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray, C: float = 0.8) -> Pipeline:
    pipe = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, C=C)),
        ]
    )
    pipe.fit(X, y, clf__sample_weight=sample_weight)
    return pipe


def predict_proba(model: Pipeline, feats: dict[str, float], alpha: float = 1.0) -> np.ndarray:
    x = np.array([[feats[c] for c in FEATURE_COLS]], dtype=float)
    ml = model.predict_proba(x)[0]
    if alpha >= 1.0:
        return np.clip(ml, 1e-6, 1 - 1e-6)
    if alpha <= 0.0:
        elo = np.array([feats["p_home_elo"], feats["p_draw_elo"], feats["p_away_elo"]])
        return np.clip(elo, 1e-6, 1 - 1e-6)
    elo = np.array([feats["p_home_elo"], feats["p_draw_elo"], feats["p_away_elo"]])
    blend = alpha * ml + (1 - alpha) * elo
    blend /= blend.sum()
    return np.clip(blend, 1e-6, 1 - 1e-6)


def evaluate_matches(
    model: Pipeline,
    engine: FeatureEngine,
    matches: pd.DataFrame,
    alpha: float = 1.0,
) -> tuple[float, list[dict]]:
    eng = clone_engine(engine)
    y_true, probs, rows_out = [], [], []

    for _, m in matches.sort_values("date").iterrows():
        home, away = norm_team(m["home_team"]), norm_team(m["away_team"])
        neutral = str(m.get("neutral", True)).lower() in ("true", "1", "t", "yes")
        date = m["date"].strftime("%Y-%m-%d") if hasattr(m["date"], "strftime") else str(m["date"])[:10]
        feats = eng.extract(
            home, away, date,
            neutral=neutral,
            tournament=m.get("tournament", WC_TOURNAMENT),
            home_conf=str(m.get("home_conf", "") or ""),
            away_conf=str(m.get("away_conf", "") or ""),
        )
        p = predict_proba(model, feats, alpha=alpha)
        y_true.append(RESULT_MAP[m["result"]])
        probs.append(p)
        rows_out.append({"home_team": home, "away_team": away, "actual": m["result"], "probs": p})
        _update_row(eng, m)

    ll = log_loss_1x2(np.array(y_true), np.array(probs))
    return ll, rows_out


def evaluate_elo_baseline(engine: FeatureEngine, matches: pd.DataFrame) -> float:
    eng = clone_engine(engine)
    y_true, probs = [], []
    for _, m in matches.sort_values("date").iterrows():
        home, away = norm_team(m["home_team"]), norm_team(m["away_team"])
        neutral = str(m.get("neutral", True)).lower() in ("true", "1", "t", "yes")
        date = m["date"].strftime("%Y-%m-%d") if hasattr(m["date"], "strftime") else str(m["date"])[:10]
        feats = eng.extract(home, away, date, neutral=neutral, tournament=m.get("tournament", WC_TOURNAMENT))
        probs.append([feats["p_home_elo"], feats["p_draw_elo"], feats["p_away_elo"]])
        y_true.append(RESULT_MAP[m["result"]])
        _update_row(eng, m)
    return log_loss_1x2(np.array(y_true), np.array(probs))


def wc_slice(df: pd.DataFrame, year: int) -> pd.DataFrame:
    return df[(df["tournament"] == WC_TOURNAMENT) & (df["date"].dt.year == year)].copy()


def train_on_slice(
    train: pd.DataFrame,
    cfg: TrainConfig,
    *,
    warm: pd.DataFrame | None = None,
) -> tuple[Pipeline, FeatureEngine]:
    X, y, engine, sw = build_training_matrix(train, cfg, warm=warm)
    model = fit_model(X, y, sw, C=cfg.C)
    return model, engine


def save_model(
    model: Pipeline,
    engine: FeatureEngine,
    cfg: TrainConfig,
    train_path: str,
    train_rows: int,
) -> dict:
    payload = {
        "model": model,
        "base_engine": engine,
        "alpha": cfg.alpha,
        "decay_lambda": cfg.decay_lambda,
        "wc_weight": cfg.wc_weight,
        "min_train_date": str(cfg.min_train_date.date()) if cfg.min_train_date is not None else None,
        "feature_cols": FEATURE_COLS,
        "train_path": train_path,
        "train_rows": train_rows,
    }
    DATA_DIR.mkdir(exist_ok=True)
    joblib.dump(payload, MODEL_PATH)
    meta = {
        "alpha": cfg.alpha,
        "decay_lambda": cfg.decay_lambda,
        "wc_weight": cfg.wc_weight,
        "major_weight": cfg.major_weight,
        "friendly_weight": cfg.friendly_weight,
        "train_path": train_path,
        "train_rows": train_rows,
        "features": len(FEATURE_COLS),
    }
    META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


def train_and_save(
    train: pd.DataFrame,
    cfg: TrainConfig | None = None,
    train_path: str = "",
    warm: pd.DataFrame | None = None,
) -> dict:
    cfg = cfg or TrainConfig(alpha=1.0, decay_lambda=0.0)
    model, engine = train_on_slice(train, cfg, warm=warm)
    return save_model(model, engine, cfg, train_path, len(train))
