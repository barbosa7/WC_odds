#!/usr/bin/env python3
"""Train the match-outcome ML model and save to wc_data/ml_match_model.joblib."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.trainer import train_and_save


def main() -> None:
    meta = train_and_save()
    print(f"Saved model trained on {meta['train_rows']:,} matches")
    print(f"  train: {meta['train_path']}")
    print(f"  features: {meta['features']}")


if __name__ == "__main__":
    main()
