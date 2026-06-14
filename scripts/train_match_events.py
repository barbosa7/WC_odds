#!/usr/bin/env python3
"""Train the goals×corners×cards product model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import load_match_stats
from ml.match_events import WC2022_KICKOFF, train_and_save


def main() -> None:
    df = load_match_stats(require_corners=True)
    comps = df.groupby("competition").size().to_dict() if "competition" in df.columns else {}
    print(f"Training data: {len(df)} matches")
    for c, n in comps.items():
        print(f"  {c}: {n}")
    print(
        f"\nHonest eval: all tournaments before {WC2022_KICKOFF.date()} "
        f"→ test WC 2022 (64 matches)\n"
    )

    meta = train_and_save(df)
    print("=== Holdout ===")
    print(json.dumps(meta.get("holdout", meta), indent=2))
    print("\n=== Walk-forward (WC seasons) ===")
    print(json.dumps(meta.get("walk_forward_wc", []), indent=2))
    print(f"\nModel saved → wc_data/match_events_model.joblib")


if __name__ == "__main__":
    main()
