#!/usr/bin/env python3
"""Train/evaluate ML model with tournament weighting; deploy best for 2026."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.evaluate import run_evaluation, train_production
from ml.martj42 import fetch_and_convert, load_train
from ml.trainer import TrainConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="ML model training and evaluation")
    parser.add_argument("--eval-only", action="store_true", help="Grid search on 2018 val, test 2022")
    parser.add_argument("--full", action="store_true", help="Production retrain with best config")
    parser.add_argument("--fetch", action="store_true", help="Refresh martj42 from GitHub")
    args = parser.parse_args()

    if args.fetch or not (ROOT / "wc_data/international_train.csv").exists():
        print("Fetching martj42 international results…")
        path = fetch_and_convert()
        df = load_train(path)
        print(f"  → {len(df):,} matches ({df.date.min().date()} → {df.date.max().date()})")

    if args.eval_only or not args.full:
        print("\n=== Tournament-weighted grid (train pre-2018, val 2018 WC, test 2022 WC) ===\n")
        summary = run_evaluation()
        bc = summary["best_config"]
        print("Best config (2018 val):", json.dumps(bc, indent=2))
        print(f"\n2018 val:              {summary['log_loss_2018_val_best']:.4f}")
        print(f"2022 test (production):  {summary['log_loss_2022_test_production']:.4f}  ({bc.get('production_pick', '')})")
        print(f"2022 extended skip-fr:   {summary['log_loss_2022_extended_uniform_skip_friendly']:.4f}")
        print(f"2022 test martj42:       {summary['log_loss_2022_test_martj42_weighted']:.4f}  (weighted grid, n={summary['n_train_pre2022_martj42']:,})")
        print(f"2022 test kaggle:          {summary['log_loss_2022_test_kaggle_weighted']:.4f}  (weighted grid, n={summary['n_train_pre2022_kaggle']:,})")
        print(f"2022 kaggle plain:         {summary['log_loss_2022_kaggle_unweighted']:.4f}")
        print(f"2022 martj42 unweighted: {summary['log_loss_2022_martj42_unweighted']:.4f}")
        print(f"2022 Elo only:           {summary['log_loss_2022_elo_only']:.4f}")
        print(f"\nProduction data pick:    {bc['production_data']}")
        print(f"Saved → output/ml_eval/metrics.json")

    if args.full:
        metrics_path = ROOT / "output/ml_eval/metrics.json"
        if not metrics_path.exists():
            print("Run --eval-only first")
            sys.exit(1)
        m = json.loads(metrics_path.read_text())
        bc = m["best_config"]
        cfg = TrainConfig(
            decay_lambda=bc["decay_lambda"],
            alpha=bc["alpha"],
            wc_weight=bc["wc_weight"],
            major_weight=bc["major_weight"],
            qual_weight=bc.get("qual_weight", 1.0),
            friendly_weight=bc["friendly_weight"],
            other_weight=bc.get("other_weight", 0.75),
            skip_friendly_lr=bc.get("skip_friendly_lr", False),
        )
        src = bc["production_data"]
        print(f"\n=== Production train ({src}) ===")
        print(json.dumps(bc, indent=2))
        meta = train_production(cfg, src)
        print(f"Saved → wc_data/ml_match_model.joblib ({meta['train_rows']:,} rows)")


if __name__ == "__main__":
    main()
