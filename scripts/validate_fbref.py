#!/usr/bin/env python3
"""Validate FBref WC cards/corners data quality and coverage."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import add_match_totals, load_match_stats

# Spot-checks: (game_id, expected totals or None to skip)
SPOT_CHECKS = {
    "7140acae": {"home": "Argentina", "away": "France", "goals": 6, "corners": 11, "cards": 8},
    "6d4b58f5": {"home": "England", "away": "France", "goals": 3, "corners": 7, "cards": 4},
    "bb30147d": {"home": "Croatia", "away": "Brazil", "goals": 2, "corners": 10, "cards": 5},
    "9fd14983": {"home": "Netherlands", "away": "Argentina", "goals": 4, "corners": 10, "cards": 19},
}

EXPECTED_MATCHES_PER_SEASON = 64


def main() -> None:
    df = add_match_totals(load_match_stats())

    print("=" * 60)
    print("FBREF DATA VALIDATION REPORT")
    print("=" * 60)

    print("\n## Coverage by competition / season")
    comp_col = "competition" if "competition" in df.columns else None
    if comp_col:
        for comp, grp in df.groupby(comp_col):
            print(f"  [{comp}]")
            for season, sgrp in grp.groupby("season"):
                corners_ok = (sgrp["total_corners"] > 0).sum()
                refs_ok = sgrp["referee"].notna().sum() if "referee" in sgrp.columns else 0
                print(f"    {season}: {len(sgrp)} matches ({corners_ok} w/ corners, {refs_ok} w/ ref)")
    else:
        for season, grp in df.groupby("season"):
            print(f"  {season}: {len(grp)} matches")

    # Missing values
    print("\n## Missing / zero checks")
    stat_cols = [
        "home_score", "away_score", "home_corners", "away_corners",
        "home_yellow", "away_yellow", "home_red", "away_red",
    ]
    for col in stat_cols:
        na = df[col].isna().sum()
        if na:
            print(f"  {col}: {na} NaN")
    zero_corners = (df["total_corners"] == 0).sum()
    if zero_corners:
        by_season = df.groupby("season").apply(lambda g: (g["total_corners"] == 0).sum())
        print(f"  Matches with 0 total corners: {zero_corners}")
        for season, n in by_season.items():
            if n:
                print(f"    {season}: {n}/64 — FBref lacks corner/foul blocks for this WC")

    pens = df[df.get("went_to_pens", False) == True]  # noqa: E712
    if len(pens):
        missing_goals = pens[pens["home_score"].isna() | pens["away_score"].isna()]
        print(f"  Penalty-shootout matches: {len(pens)} ({len(missing_goals)} missing ET score)")

    # Spot checks
    print("\n## Spot-checks (known matches)")
    for gid, exp in SPOT_CHECKS.items():
        row = df[df["game_id"] == gid]
        if row.empty:
            print(f"  {gid} {exp['home']} vs {exp['away']}: MISSING")
            continue
        r = row.iloc[0]
        tg = int(r["total_goals"]) if pd.notna(r["total_goals"]) else None
        tc = int(r["total_corners"])
        tca = int(r["total_cards"])
        ok = tg == exp["goals"] and tc == exp["corners"] and tca == exp["cards"]
        mark = "PASS" if ok else "FAIL"
        print(
            f"  [{mark}] {exp['home']} vs {exp['away']}: "
            f"goals={tg} (exp {exp['goals']}), corners={tc} (exp {exp['corners']}), "
            f"cards={tca} (exp {exp['cards']}), g×c×c={r['gxcxc']:.0f}"
        )

    # Distribution summary
    print("\n## Target distribution (goals × corners × cards)")
    for col in ("total_goals", "total_corners", "total_cards", "gxcxc"):
        s = df[col].dropna()
        print(f"  {col}: mean={s.mean():.1f}, median={s.median():.0f}, min={s.min():.0f}, max={s.max():.0f}")

    # Sufficiency assessment
    print("\n## Sufficiency for modeling")
    n = len(df.dropna(subset=["total_goals"]))
    n_corners = len(df[df["total_corners"] > 0].dropna(subset=["total_goals"]))
    if n_corners < 128:
        print(f"  ⚠ Only {n_corners} matches with corner data — 2010 (and earlier) lack FBref corners")
        print(f"  → Product model uses 2014/2018/2022 only ({n_corners} matches)")
    elif n_corners < 256:
        print(f"  {n_corners} matches with full goals+corners+cards (2014–2022)")
    else:
        print(f"  {n_corners} matches — adequate for WC-only product model")

    print("\n## WC outcome model (1X2) feature potential")
    print("  Cards/corners are weak direct predictors of match result.")
    print("  May help slightly via team style (aggressive vs passive) — run eval_fbref_features.py")

    print("\n## ET / penalty note")
    print("  FBref team_stats include extra time; penalty shootout events are excluded.")
    print("  Goals parsed from schedule ET score (e.g. 3–3), not pen tally (4–2).")


if __name__ == "__main__":
    main()
