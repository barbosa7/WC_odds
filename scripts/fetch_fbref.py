#!/usr/bin/env python3
"""Fetch FBref tournament cards/corners/referees into wc_data/fbref_match_stats.csv."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import (
    DEFAULT_EURO_SEASONS,
    DEFAULT_WC_SEASONS,
    fetch_all_tournament_stats,
    fetch_euro_stats,
    fetch_world_cup_stats,
    referee_summary,
    save_match_stats,
    team_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch FBref international tournament stats")
    parser.add_argument(
        "--competition",
        choices=("wc", "euro", "all"),
        default="wc",
        help="Which competition to fetch (default: wc)",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=None,
        help="Years to fetch (default depends on --competition)",
    )
    parser.add_argument("--force-cache", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    print("(Uses soccerdata + browser — first run is slow; pages are cached locally.)\n")

    if args.competition == "all":
        wc = tuple(args.seasons) if args.seasons else DEFAULT_WC_SEASONS
        df = fetch_all_tournament_stats(wc_seasons=wc, euro_seasons=DEFAULT_EURO_SEASONS)
    elif args.competition == "euro":
        seasons = tuple(args.seasons) if args.seasons else DEFAULT_EURO_SEASONS
        print(f"Fetching European Championship: {', '.join(seasons)}")
        df = fetch_euro_stats(seasons)
    else:
        seasons = tuple(args.seasons) if args.seasons else DEFAULT_WC_SEASONS
        print(f"Fetching World Cup: {', '.join(seasons)}")
        df = fetch_world_cup_stats(seasons)

    out = save_match_stats(df)
    print(f"\nSaved {len(df):,} matches → {out}")
    if "competition" in df.columns:
        print(df.groupby("competition").size().to_string())

    if args.summary:
        team_summary(df).to_csv(ROOT / "wc_data" / "fbref_team_summary.csv", index=False)
        referee_summary(df).to_csv(ROOT / "wc_data" / "fbref_referee_summary.csv", index=False)
        print("Summaries → wc_data/fbref_team_summary.csv, fbref_referee_summary.csv")


if __name__ == "__main__":
    main()
