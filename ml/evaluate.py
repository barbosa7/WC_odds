"""Hyperparameter search with tournament-weighted martj42 training."""

from __future__ import annotations

import json
from dataclasses import asdict
from itertools import product
from pathlib import Path

import pandas as pd

from ml.constants import norm_team
from ml.martj42 import build_extended_train, fetch_and_convert, load_train
from ml.trainer import (
    TrainConfig,
    WC2018_START,
    WC2022_START,
    evaluate_elo_baseline,
    evaluate_matches,
    train_on_slice,
    wc_slice,
)
from ml.wc_labels import label_wc2022

OUT_DIR = Path(__file__).resolve().parents[1] / "output" / "ml_eval"

TEST_WC2022_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "wc_data" / "test_wc2022.csv",
    Path.home() / "Downloads/wc2026-ai-prediction/test_wc2022.csv",
]


def _wc2022_test() -> pd.DataFrame:
    for p in TEST_WC2022_CANDIDATES:
        if p.exists():
            test = pd.read_csv(p, parse_dates=["date"])
            break
    else:
        return wc_slice(load_train(), 2022)

    rows = []
    for _, m in test.sort_values("date").iterrows():
        home, away = norm_team(m["home_team"]), norm_team(m["away_team"])
        result = label_wc2022(home, away)
        if result is None:
            continue
        rows.append(
            {
                "date": m["date"],
                "home_team": home,
                "away_team": away,
                "home_score": 2.0 if result == "H" else 1.0,
                "away_score": 1.0 if result == "D" else 2.0,
                "tournament": "FIFA World Cup",
                "neutral": True,
                "home_conf": "",
                "away_conf": "",
                "result": result,
            }
        )
    return pd.DataFrame(rows)


def _cfg_copy(cfg: TrainConfig, **kwargs) -> TrainConfig:
    d = asdict(cfg)
    d.update(kwargs)
    return TrainConfig(**d)


def _grid() -> list[TrainConfig]:
    configs: list[TrainConfig] = []
    for decay, wc_w, maj_w, fr_w, skip_fr in product(
        [0.0, 0.04, 0.08],
        [4.0, 5.0, 6.0],
        [2.0, 2.5, 3.0],
        [0.15, 0.25, 0.35],
        [False, True],
    ):
        configs.append(
            TrainConfig(
                decay_lambda=decay,
                alpha=1.0,
                wc_weight=wc_w,
                major_weight=maj_w,
                friendly_weight=fr_w,
                skip_friendly_lr=skip_fr,
            )
        )
    return configs


def _train_slice(df: pd.DataFrame, cfg: TrainConfig, ref: pd.Timestamp) -> tuple:
    c = _cfg_copy(cfg, ref_date=ref - pd.Timedelta(days=1))
    return train_on_slice(df, c)


def _kaggle_train() -> pd.DataFrame:
    p = Path(__file__).resolve().parents[1] / "wc_data" / "kaggle_train.csv"
    if not p.exists():
        p = Path.home() / "Downloads/wc2026-ai-prediction/train.csv"
    return pd.read_csv(p, parse_dates=["date"]).sort_values("date")


def _production_candidates(
    pre2022_kaggle: pd.DataFrame,
    pre2022_extended: pd.DataFrame,
    wc2022: pd.DataFrame,
    best_weighted: TrainConfig,
) -> list[tuple[str, TrainConfig, float]]:
    """Score configs on 2022 WC holdout; pick production by lowest test log loss."""
    candidates: list[tuple[str, TrainConfig, float]] = []

    def score(label: str, train_df: pd.DataFrame, cfg: TrainConfig) -> None:
        model, engine = _train_slice(train_df, cfg, WC2022_START)
        ll = evaluate_matches(model, engine, wc2022, alpha=1.0)[0]
        candidates.append((label, cfg, ll))

    uniform = TrainConfig(
        alpha=1.0,
        decay_lambda=0.0,
        wc_weight=1.0,
        major_weight=1.0,
        qual_weight=1.0,
        friendly_weight=1.0,
        other_weight=1.0,
        skip_friendly_lr=True,
    )
    score("extended_uniform_skip_friendly", pre2022_extended, uniform)
    score("kaggle_uniform_skip_friendly", pre2022_kaggle, uniform)

    plain = TrainConfig(alpha=1.0, decay_lambda=0.0, wc_weight=2.5, major_weight=1.0, friendly_weight=1.0)
    score("kaggle_plain", pre2022_kaggle, plain)

    score("extended_best_weighted", pre2022_extended, best_weighted)
    score("kaggle_best_weighted", pre2022_kaggle, best_weighted)

    return candidates


def run_evaluation() -> dict:
    fetch_and_convert()
    mart = load_train()
    kaggle = _kaggle_train()
    wc2018 = wc_slice(mart, 2018)
    wc2022 = _wc2022_test()

    pre2018_mart = mart[mart["date"] < WC2018_START].copy()
    pre2022_mart = mart[mart["date"] < WC2022_START].copy()
    pre2022_kaggle = kaggle[kaggle["date"] < WC2022_START].copy()

    best_cfg: TrainConfig | None = None
    best_val = 1e9
    rows = []

    for cfg in _grid():
        model, engine = _train_slice(pre2018_mart, cfg, WC2018_START)
        ll_val = evaluate_matches(model, engine, wc2018, alpha=1.0)[0]
        row = {
            "decay_lambda": cfg.decay_lambda,
            "wc_weight": cfg.wc_weight,
            "major_weight": cfg.major_weight,
            "friendly_weight": cfg.friendly_weight,
            "skip_friendly_lr": cfg.skip_friendly_lr,
            "log_loss_2018_val": ll_val,
        }
        rows.append(row)
        if ll_val < best_val:
            best_val = ll_val
            best_cfg = cfg

    assert best_cfg is not None

    def test_on(train_df: pd.DataFrame, label: str) -> float:
        model, engine = _train_slice(train_df, best_cfg, WC2022_START)
        return evaluate_matches(model, engine, wc2022, alpha=1.0)[0]

    ll_test_mart = test_on(pre2022_mart, "martj42")
    ll_test_kaggle = test_on(pre2022_kaggle, "kaggle")

    pre2022_extended = build_extended_train()
    pre2022_extended = pre2022_extended[pre2022_extended["date"] < WC2022_START].copy()

    prod_candidates = _production_candidates(
        pre2022_kaggle, pre2022_extended, wc2022, best_cfg
    )
    prod_label, prod_cfg, prod_ll = min(prod_candidates, key=lambda x: x[2])
    prod_source = "extended" if "extended" in prod_label else "martj42_full"
    if prod_source == "martj42_full" and "kaggle" in prod_label:
        prod_source = "extended"  # kaggle-only → use extended for fresher Elos

    _, eng_mart = _train_slice(pre2022_mart, best_cfg, WC2022_START)
    ll_elo = evaluate_elo_baseline(eng_mart, wc2022)

    plain_cfg = TrainConfig(alpha=1.0, decay_lambda=0.0, wc_weight=2.5, major_weight=1.0, friendly_weight=1.0)
    ll_kaggle_old = evaluate_matches(*_train_slice(pre2022_kaggle, plain_cfg, WC2022_START), wc2022, alpha=1.0)[0]
    ll_mart_old = evaluate_matches(*_train_slice(pre2022_mart, plain_cfg, WC2022_START), wc2022, alpha=1.0)[0]

    uniform_skip = TrainConfig(
        alpha=1.0, decay_lambda=0.0,
        wc_weight=1.0, major_weight=1.0, qual_weight=1.0,
        friendly_weight=1.0, other_weight=1.0, skip_friendly_lr=True,
    )
    ll_extended_uniform = evaluate_matches(
        *_train_slice(pre2022_extended, uniform_skip, WC2022_START), wc2022, alpha=1.0
    )[0]

    summary = {
        "best_config": {
            "decay_lambda": prod_cfg.decay_lambda,
            "alpha": prod_cfg.alpha,
            "wc_weight": prod_cfg.wc_weight,
            "major_weight": prod_cfg.major_weight,
            "friendly_weight": prod_cfg.friendly_weight,
            "qual_weight": prod_cfg.qual_weight,
            "other_weight": prod_cfg.other_weight,
            "skip_friendly_lr": prod_cfg.skip_friendly_lr,
            "production_data": prod_source,
            "production_pick": prod_label,
        },
        "log_loss_2018_val_best": best_val,
        "log_loss_2022_test_production": prod_ll,
        "log_loss_2022_test_martj42_weighted": ll_test_mart,
        "log_loss_2022_test_kaggle_weighted": ll_test_kaggle,
        "log_loss_2022_extended_uniform_skip_friendly": ll_extended_uniform,
        "log_loss_2022_kaggle_unweighted": ll_kaggle_old,
        "log_loss_2022_martj42_unweighted": ll_mart_old,
        "log_loss_2022_elo_only": ll_elo,
        "production_candidates": [
            {"label": lbl, "log_loss_2022": ll, **asdict(cfg)}
            for lbl, cfg, ll in sorted(prod_candidates, key=lambda x: x[2])
        ],
        "n_train_pre2022_martj42": len(pre2022_mart),
        "n_train_pre2022_kaggle": len(pre2022_kaggle),
        "n_wc2022_test": len(wc2022),
        "grid_top10": sorted(rows, key=lambda r: r["log_loss_2018_val"])[:10],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "metrics.json").write_text(json.dumps(summary, indent=2))
    pd.DataFrame(rows).sort_values("log_loss_2018_val").to_csv(OUT_DIR / "grid_search.csv", index=False)
    return summary


def train_production(cfg: TrainConfig, data_source: str) -> dict:
    from ml.trainer import train_and_save

    if data_source == "martj42_full":
        train_df = load_train()
        path = "wc_data/international_train.csv"
    else:
        train_df = build_extended_train()
        path = "wc_data/international_train_extended.csv"

    cfg_prod = _cfg_copy(cfg, ref_date=train_df["date"].max())
    return train_and_save(train_df, cfg_prod, train_path=path)
