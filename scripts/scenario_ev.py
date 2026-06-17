#!/usr/bin/env python3
"""Compare expected points under hypothetical match outcomes."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from simulate import run_monte_carlo
from wc_results import load_completed_matches

BASE_RESULTS = ROOT / "wc_data" / "completed_matches.json"
OUT_PATH = ROOT / "output" / "scenarios.json"


def run_scenario(
    base_matches: list[dict],
    extra: dict,
    *,
    n_sims: int,
    seed: int,
) -> dict:
    matches = base_matches + [extra]
    tmp = ROOT / "wc_data" / "_scenario_tmp.json"
    tmp.write_text(json.dumps({"matches": matches}, indent=2))
    try:
        ctx = load_completed_matches(tmp)
        return run_monte_carlo(n_sims=n_sims, seed=seed, use_ml=True, conditional=ctx)
    finally:
        tmp.unlink(missing_ok=True)


def ev_by_team(result: dict) -> dict[str, float]:
    return {t["team"]: t["expected_points"] for t in result["teams"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scenario EV comparison")
    parser.add_argument("-n", "--simulations", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    base = json.loads(BASE_RESULTS.read_text())["matches"]
    pre = json.loads((ROOT / "output" / "expected_points.json").read_text())
    pre_ev = ev_by_team(pre)

    tmp = ROOT / "wc_data" / "_scenario_tmp.json"
    tmp.write_text(json.dumps({"matches": base}, indent=2))
    baseline_ctx = load_completed_matches(tmp)
    tmp.unlink(missing_ok=True)
    baseline = run_monte_carlo(
        n_sims=args.simulations, seed=args.seed, use_ml=True, conditional=baseline_ctx,
    )
    baseline_ev = ev_by_team(baseline)

    fixtures = [
        {
            "label": "Brazil vs Morocco",
            "teams": ["Brazil", "Morocco"],
            "scenarios": [
                {"name": "Brazil 2-0", "home": "Brazil", "away": "Morocco", "home_score": 2, "away_score": 0},
                {"name": "1-1 draw", "home": "Brazil", "away": "Morocco", "home_score": 1, "away_score": 1},
                {"name": "Morocco 1-0", "home": "Morocco", "away": "Brazil", "home_score": 1, "away_score": 0},
            ],
        },
        {
            "label": "Switzerland vs Qatar",
            "teams": ["Switzerland", "Qatar"],
            "scenarios": [
                {"name": "Switzerland 2-0", "home": "Switzerland", "away": "Qatar", "home_score": 2, "away_score": 0},
                {"name": "1-1 draw", "home": "Switzerland", "away": "Qatar", "home_score": 1, "away_score": 1},
                {"name": "Qatar 1-0", "home": "Qatar", "away": "Switzerland", "home_score": 1, "away_score": 0},
            ],
        },
    ]

    output: dict = {
        "n_simulations": args.simulations,
        "base_matches": len(base),
        "fixtures": [],
    }

    for fix in fixtures:
        fix_out = {"label": fix["label"], "teams": fix["teams"], "scenarios": []}
        print(f"\n=== {fix['label']} ({args.simulations:,} sims each) ===\n")
        header = f"{'Scenario':<18}" + "".join(f"{t:>14}" for t in fix["teams"])
        header += f"{'Δ vs now':>10}" * len(fix["teams"])
        print(header)
        print("-" * len(header))

        now_row = f"{'Now (no result)':<18}" + "".join(
            f"{baseline_ev.get(t, 0):>14.1f}" for t in fix["teams"]
        )
        now_row += "".join(
            f"{baseline_ev.get(t, 0) - pre_ev.get(t, 0):>+10.1f}" for t in fix["teams"]
        )
        print(now_row)

        fix_out["scenarios"].append({
            "name": "Now (no result)",
            "match": None,
            "expected_points": {t: round(baseline_ev.get(t, 0), 2) for t in fix["teams"]},
            "delta_vs_pre": {t: round(baseline_ev.get(t, 0) - pre_ev.get(t, 0), 2) for t in fix["teams"]},
            "delta_vs_now": {t: 0.0 for t in fix["teams"]},
        })

        for sc in fix["scenarios"]:
            result = run_scenario(base, sc, n_sims=args.simulations, seed=args.seed)
            ev = ev_by_team(result)
            deltas = {t: ev.get(t, 0) - baseline_ev.get(t, 0) for t in fix["teams"]}
            row = f"{sc['name']:<18}" + "".join(f"{ev.get(t, 0):>14.1f}" for t in fix["teams"])
            row += "".join(f"{deltas[t]:>+10.1f}" for t in fix["teams"])
            print(row)

            fix_out["scenarios"].append({
                "name": sc["name"],
                "match": {
                    "home": sc["home"],
                    "away": sc["away"],
                    "home_score": sc["home_score"],
                    "away_score": sc["away_score"],
                },
                "expected_points": {t: round(ev.get(t, 0), 2) for t in fix["teams"]},
                "delta_vs_pre": {t: round(ev.get(t, 0) - pre_ev.get(t, 0), 2) for t in fix["teams"]},
                "delta_vs_now": {t: round(deltas[t], 2) for t in fix["teams"]},
            })

        output["fixtures"].append(fix_out)

    OUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nSaved → {OUT_PATH}")


if __name__ == "__main__":
    main()
