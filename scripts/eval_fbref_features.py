#!/usr/bin/env python3
"""Test whether FBref cards/corners team priors improve WC 1X2 log loss."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.constants import RESULT_MAP
from ml.fbref import load_match_stats, team_summary
from ml.features import FEATURE_COLS
from ml.trainer import (
    WC2022_START,
    TrainConfig,
    build_training_matrix,
    evaluate_matches,
    fit_model,
    log_loss_1x2,
    warm_engine,
)

DATA = ROOT / "wc_data" / "international_train_extended.csv"


def _fbref_lookup(season: int = 2022) -> pd.DataFrame:
    fb = load_match_stats()
    prior = fb[fb["season"] < season]
    if prior.empty:
        raise ValueError(
            f"No FBref seasons before {season} — cannot build leakage-free lookup for WC eval"
        )
    return team_summary(prior).set_index("team").rename(
        columns={"corners_pg": "corners", "yellow_pg": "yellow", "red_pg": "red"}
    )


def _extra_feats(home: str, away: str, lookup: pd.DataFrame) -> list[float]:
    mean = lookup.mean()
    h = lookup.loc[home] if home in lookup.index else mean
    a = lookup.loc[away] if away in lookup.index else mean
    return [
        h["corners"], a["corners"],
        h["yellow"], a["yellow"],
        h["red"], a["red"],
        h["corners"] + a["corners"],
        h["yellow"] + a["yellow"],
    ]


def main() -> None:
    train_all = pd.read_csv(DATA, parse_dates=["date"])
    test = train_all[
        (train_all["tournament"] == "FIFA World Cup") & (train_all["date"] >= WC2022_START)
    ].sort_values("date")
    train = train_all[train_all["date"] < WC2022_START]

    cfg = TrainConfig(skip_friendly_lr=True)
    X, y, engine, w = build_training_matrix(train, cfg)
    model = fit_model(X, y, w, C=cfg.C)
    ll_base, _ = evaluate_matches(model, engine, test, alpha=1.0)

    lookup = _fbref_lookup(2022)
    train_sorted = train.sort_values("date")
    train_rows = train_sorted[
        ~(
            (train_sorted["tournament"] == "Friendly")
            & cfg.skip_friendly_lr
        )
    ]
    if cfg.min_train_date:
        train_rows = train_rows[train_rows["date"] >= cfg.min_train_date]

    # Re-extract features in same order as build_training_matrix
    eng = warm_engine(train, upto=None)
    X_rows, y_rows, w_rows = [], [], []
    for _, m in train.sort_values("date").iterrows():
        if cfg.skip_friendly_lr and m["tournament"] == "Friendly":
            from ml.trainer import _update_row
            _update_row(eng, m)
            continue
        neutral = str(m["neutral"]).lower() in ("true", "1", "t")
        feats = eng.extract(
            m["home_team"], m["away_team"], m["date"],
            neutral=neutral, tournament=m["tournament"],
        )
        X_rows.append([feats[c] for c in FEATURE_COLS] + _extra_feats(m["home_team"], m["away_team"], lookup))
        y_rows.append(RESULT_MAP[m["result"]])
        from ml.trainer import _row_weight, _update_row
        w_rows.append(_row_weight(m, cfg))
        _update_row(eng, m)

    X_ext = np.array(X_rows, dtype=float)
    pipe_ext = Pipeline([
        ("s", StandardScaler()),
        ("lr", LogisticRegression(C=cfg.C, max_iter=2000)),
    ])
    pipe_ext.fit(X_ext, y_rows, lr__sample_weight=np.array(w_rows))

    warm = warm_engine(train)
    y_test, probs = [], []
    eng2 = warm
    for _, m in test.iterrows():
        neutral = str(m.get("neutral", True)).lower() in ("true", "1", "t", "yes")
        feats = eng2.extract(m["home_team"], m["away_team"], m["date"], neutral=neutral, tournament=m["tournament"])
        x = np.array([[feats[c] for c in FEATURE_COLS] + _extra_feats(m["home_team"], m["away_team"], lookup)])
        probs.append(pipe_ext.predict_proba(x)[0])
        y_test.append(RESULT_MAP[m["result"]])
        from ml.trainer import _update_row
        _update_row(eng2, m)

    ll_ext = log_loss_1x2(np.array(y_test), np.array(probs))

    print("FBref feature utility — WC 2022 holdout (1X2 log loss, lower = better)")
    print("  (Main model trains on all pre-2022 int'l matches; FBref lookup uses 2014+2018 WC only)")
    print(f"  Baseline:              {ll_base:.4f}")
    print(f"  + FBref corners/cards: {ll_ext:.4f}")
    delta = ll_ext - ll_base
    verdict = "helps" if delta < -0.002 else "no meaningful gain"
    print(f"  Delta:                 {delta:+.4f} ({verdict})")
    print(f"  FBref lookup: {len(lookup)} teams from pre-2022 WC seasons")


if __name__ == "__main__":
    main()
