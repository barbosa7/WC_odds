#!/usr/bin/env python3
"""Run WC expected-points analysis and write outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from parse_oddschecker import parse_all
from simulate import run_monte_carlo
from wc_results import load_completed_matches


def main() -> None:
    parser = argparse.ArgumentParser(description="WC 2026 expected points from odds + simulation")
    parser.add_argument("-n", "--simulations", type=int, default=25_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--no-ml",
        action="store_true",
        help="Use Oddschecker odds only (no Kaggle ML model)",
    )
    parser.add_argument(
        "--odds-weight",
        type=float,
        default=0.35,
        help="Share of Oddschecker 1X2 in group-stage blend when ML is on (default 0.35)",
    )
    parser.add_argument(
        "--train-ml",
        action="store_true",
        help="Retrain ML model from Kaggle train.csv before simulating",
    )
    parser.add_argument(
        "--both-models",
        action="store_true",
        help="Run ML and odds-only sims (writes both JSON files for dashboard)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="JSON file with completed group-stage scores (see wc_data/completed_matches.json)",
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Only run conditional sim from --results (skip pre-tournament baseline)",
    )
    args = parser.parse_args()

    if args.current_only and not args.results:
        parser.error("--current-only requires --results")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Always refresh odds from saved Oddschecker HTML exports
    from pathlib import Path as P
    cache = P("wc_data/odds_oddschecker.json")
    cache.write_text(__import__("json").dumps(parse_all(), indent=2))

    if args.train_ml:
        from ml.martj42 import build_extended_train, load_extended_train
        from ml.trainer import TrainConfig, train_and_save

        df = load_extended_train() if (Path("wc_data/international_train_extended.csv")).exists() else build_extended_train()
        meta = train_and_save(
            df,
            TrainConfig(alpha=1.0, decay_lambda=0.05, ref_date=df["date"].max()),
            train_path=str(Path("wc_data/international_train_extended.csv")),
        )
        print(f"Trained ML model on {meta['train_rows']:,} matches → wc_data/ml_match_model.joblib")

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

    def write_outputs(result: dict, out_dir: Path, label: str) -> None:
        json_path = out_dir / "expected_points.json"
        json_path.write_text(json.dumps(result, indent=2))

        csv_path = out_dir / "expected_points.csv"
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in result["teams"]:
                w.writerow(row)

        print(f"\n=== {label} ===")
        print(f"Simulations: {result['n_simulations']:,}")
        mode = "ML + Oddschecker" if result.get("use_ml", True) else "Oddschecker only"
        print(f"Mode: {mode}")
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

    def run_current_sim(use_ml: bool, out_path: Path, label: str) -> None:
        ctx = load_completed_matches(args.results)
        print(f"\nCompleted matches ({len(ctx.matches)}):")
        for m in ctx.matches:
            print(f"  MD{m.matchday} Group {m.group}: {m.home} {m.home_score}–{m.away_score} {m.away}")
        result = run_monte_carlo(
            n_sims=args.simulations,
            seed=args.seed,
            use_ml=use_ml,
            odds_weight=args.odds_weight,
            conditional=ctx,
        )
        pre_path = args.output_dir / "expected_points.json"
        pre_by_team = {}
        if pre_path.exists():
            pre = json.loads(pre_path.read_text())
            pre_by_team = {t["team"]: t["expected_points"] for t in pre.get("teams", [])}
        for row in result["teams"]:
            row["expected_points_pre"] = pre_by_team.get(row["team"])
            if row["expected_points_pre"] is not None:
                row["expected_points_delta"] = round(
                    row["expected_points"] - row["expected_points_pre"], 2
                )
        out_path.write_text(json.dumps(result, indent=2))
        print(f"\n=== {label} (current) ===")
        print(f"Simulations: {result['n_simulations']:,}")
        print(f"\nTop 15 by current expected points:\n")
        print(f"{'Team':<28} {'Current':>8} {'Pre':>8} {'Δ':>7}")
        print("-" * 55)
        for row in result["teams"][:15]:
            pre = row.get("expected_points_pre")
            delta = row.get("expected_points_delta")
            pre_s = f"{pre:>8.1f}" if pre is not None else f"{'—':>8}"
            delta_s = f"{delta:>+7.1f}" if delta is not None else f"{'—':>7}"
            print(
                f"{row['team']:<28} {row['expected_points']:>8.1f} "
                f"{pre_s} {delta_s}"
            )
        print(f"\nCurrent EV: {out_path}")

    if args.both_models:
        if not args.current_only:
            result_ml = run_monte_carlo(
                n_sims=args.simulations,
                seed=args.seed,
                use_ml=True,
                odds_weight=args.odds_weight,
            )
            write_outputs(result_ml, args.output_dir, "ML + Oddschecker")

            odds_dir = args.output_dir / "odds_only"
            odds_dir.mkdir(parents=True, exist_ok=True)
            result_odds = run_monte_carlo(
                n_sims=args.simulations,
                seed=args.seed,
                use_ml=False,
                odds_weight=args.odds_weight,
            )
            write_outputs(result_odds, odds_dir, "Oddschecker only")

            compare_path = args.output_dir / "expected_points_odds_only.json"
            compare_path.write_text(json.dumps(result_odds, indent=2))
            print(f"\nDashboard comparison file: {compare_path}")

        if args.results:
            run_current_sim(
                use_ml=True,
                out_path=args.output_dir / "expected_points_current.json",
                label="ML + Oddschecker",
            )
            run_current_sim(
                use_ml=False,
                out_path=args.output_dir / "expected_points_current_odds_only.json",
                label="Oddschecker only",
            )
        return

    if args.current_only:
        run_current_sim(
            use_ml=not args.no_ml,
            out_path=args.output_dir / "expected_points_current.json",
            label="ML + Oddschecker" if not args.no_ml else "Oddschecker only",
        )
        return

    result = run_monte_carlo(
        n_sims=args.simulations,
        seed=args.seed,
        use_ml=not args.no_ml,
        odds_weight=args.odds_weight,
    )
    write_outputs(result, args.output_dir, "ML + Oddschecker" if not args.no_ml else "Oddschecker only")

    if args.results:
        run_current_sim(
            use_ml=not args.no_ml,
            out_path=args.output_dir / "expected_points_current.json",
            label="ML + Oddschecker" if not args.no_ml else "Oddschecker only",
        )


if __name__ == "__main__":
    main()
