#!/usr/bin/env python3
"""Backfill referee names from cached FBref HTML into fbref_match_stats.csv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import OUT_PATH, backfill_referees_from_cache, referee_summary, save_match_stats


def main() -> None:
    df = backfill_referees_from_cache()
    save_match_stats(df)
    n_refs = int(df["referee"].notna().sum())
    print(f"\nSaved {len(df)} matches ({n_refs} with referee) → {OUT_PATH}")

    summary = referee_summary(df)
    summary_path = ROOT / "wc_data" / "fbref_referee_summary.json"
    summary_path.write_text(json.dumps(summary.head(25).to_dict(orient="records"), indent=2))
    print(f"Ref summary → {summary_path}\n")
    print(summary.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
