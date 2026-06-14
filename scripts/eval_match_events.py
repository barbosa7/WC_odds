#!/usr/bin/env python3
"""Train and report match-events model evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import load_match_stats
from ml.match_events import train_and_save


def main() -> None:
    df = load_match_stats(require_corners=True)
    print(f"Dataset: {len(df)} matches (WC + Euro, corners required)\n")
    meta = train_and_save(df)

    h = meta["holdout"]["wc2022_holdout"]
    print("=" * 60)
    print("WC 2022 HOLDOUT (primary — train all pre-Nov 2022, calibrate on 2018)")
    print("=" * 60)
    print(json.dumps(h, indent=2))

    print("\nRaw Tweedie (uncalibrated) on same holdout:")
    print(json.dumps(meta["holdout"]["wc2022_raw_tweedie"], indent=2))

    print("\nWalk-forward WC seasons:")
    for row in meta["walk_forward_wc"]:
        print(f"  {row['test_season']}: MAE={row['mae']} bias={row['bias']:+.1f} "
              f"spearman={row['spearman']} n={row['n']}")

    print(f"\nModel → wc_data/match_events_model.joblib")
    print(f"Eval  → output/match_events_eval.json")


if __name__ == "__main__":
    main()
