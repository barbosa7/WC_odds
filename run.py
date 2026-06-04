#!/usr/bin/env python3
"""Run WC expected-points analysis and write outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from parse_oddschecker import parse_all
from simulate import run_monte_carlo


def main() -> None:
    parser = argparse.ArgumentParser(description="WC 2026 expected points from odds + simulation")
    parser.add_argument("-n", "--simulations", type=int, default=25_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Always refresh odds from saved Oddschecker HTML exports
    from pathlib import Path as P
    cache = P("wc_data/odds_oddschecker.json")
    cache.write_text(__import__("json").dumps(parse_all(), indent=2))

    result = run_monte_carlo(n_sims=args.simulations, seed=args.seed)

    json_path = args.output_dir / "expected_points.json"
    json_path.write_text(json.dumps(result, indent=2))

    csv_path = args.output_dir / "expected_points.csv"
    fields = [
        "team",
        "expected_points",
        "p_champion",
        "p_runner_up",
        "p_third_place",
        "p_semi_final",
        "p_quarter_final",
        "p_round_of_16",
        "p_round_of_32",
        "p_group_1",
        "p_group_2",
        "p_group_3",
        "p_group_4",
        "p_bonus_goals",
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in result["teams"]:
            w.writerow(row)

    print(f"Simulations: {result['n_simulations']:,}")
    print(f"Odds sources: {', '.join(result['odds_sources'])}")
    if result.get("missing_outright"):
        print(f"Warning: no winner odds for: {', '.join(result['missing_outright'])}")
    print(f"\nTop 15 by expected points:\n")
    print(f"{'Team':<28} {'E[Pts]':>8} {'P(W)':>7} {'P(SF)':>7} {'P(QF)':>7} {'P(R16)':>7}")
    print("-" * 68)
    for row in result["teams"][:15]:
        print(
            f"{row['team']:<28} {row['expected_points']:>8.1f} "
            f"{row['p_champion']:>7.1%} {row['p_semi_final']:>7.1%} "
            f"{row['p_quarter_final']:>7.1%} {row['p_round_of_16']:>7.1%}"
        )
    print(f"\nFull results: {json_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
