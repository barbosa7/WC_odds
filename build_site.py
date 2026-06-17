#!/usr/bin/env python3
"""Build static site into dist/ for Netlify (or any static host)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web"
DIST = ROOT / "dist"
DATA_OUT = DIST / "data"

REQUIRED = {
    "expected_points.json": ROOT / "output" / "expected_points.json",
    "expected_points_odds_only.json": ROOT / "output" / "expected_points_odds_only.json",
    "tournament.json": ROOT / "wc_data" / "tournament.json",
    "odds_oddschecker.json": ROOT / "wc_data" / "odds_oddschecker.json",
}

OPTIONAL = {
    "expected_points_current.json": ROOT / "output" / "expected_points_current.json",
    "expected_points_current_odds_only.json": ROOT / "output" / "expected_points_current_odds_only.json",
    "tychemkt_opportunities.json": ROOT / "output" / "tychemkt_opportunities.json",
    "match_events_predictions.json": ROOT / "output" / "match_events_predictions.json",
}


def run_simulation(n_sims: int) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "-n", str(n_sims), "--both-models"],
        check=True,
        cwd=ROOT,
    )


def build(*, run_sim: bool = False, n_sims: int = 25_000) -> None:
    if run_sim:
        run_simulation(n_sims)

    missing = [name for name, path in REQUIRED.items() if not path.exists()]
    if missing:
        print("Missing required data files:", ", ".join(missing))
        print("Run: python run.py")
        print("Or rebuild with: python build_site.py --run-simulation")
        sys.exit(1)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    DATA_OUT.mkdir()

    for src in WEB.iterdir():
        if src.is_file():
            shutil.copy2(src, DIST / src.name)

    for out_name, src_path in REQUIRED.items():
        shutil.copy2(src_path, DATA_OUT / out_name)

    for out_name, src_path in OPTIONAL.items():
        if src_path.exists():
            shutil.copy2(src_path, DATA_OUT / out_name)

    redirects = DIST / "_redirects"
    redirects.write_text("/login /login.html 200\n")

    print(f"Built static site → {DIST}")
    print(f"  {len(list(DIST.rglob('*')))} files")
    print("  Deploy dist/ to Netlify, or run: python serve_web.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Netlify-ready static dashboard")
    parser.add_argument(
        "--run-simulation",
        action="store_true",
        help="Run full simulation before building (slow; use on Netlify CI)",
    )
    parser.add_argument("-n", "--simulations", type=int, default=25_000)
    args = parser.parse_args()
    build(run_sim=args.run_simulation, n_sims=args.simulations)


if __name__ == "__main__":
    main()
