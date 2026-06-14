#!/usr/bin/env python3
"""Predict E[goals×corners×cards] for 2026 fixtures; uses published refs when known."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.fbref import _norm_referee
from ml.match_events import load_model

PUBLISHED_REFS = ROOT / "wc_data" / "published_refs_2026.json"
TOURNAMENT = ROOT / "wc_data" / "tournament.json"
OUT = ROOT / "output" / "match_events_predictions.json"


def _load_published_refs() -> dict[tuple[str, str], str]:
    if not PUBLISHED_REFS.exists():
        return {}
    rows = json.loads(PUBLISHED_REFS.read_text())
    out = {}
    for r in rows:
        key = (r["home"], r["away"])
        out[key] = _norm_referee(r["referee"])
        out[(r["away"], r["home"])] = out[key]  # not used but safe
    return out


def group_stage_fixtures() -> list[dict]:
    t = json.loads(TOURNAMENT.read_text())
    refs = _load_published_refs()
    fixtures = []
    for group, teams in t["groups"].items():
        for md, pairs in enumerate(t["group_matchdays"], 1):
            for i, j in pairs:
                home, away = teams[i], teams[j]
                ref = refs.get((home, away))
                fixtures.append({
                    "group": group,
                    "matchday": md,
                    "home": home,
                    "away": away,
                    "referee": ref,
                })
    return fixtures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-stage-only", action="store_true", default=True)
    parser.add_argument("-o", "--output", default=str(OUT))
    args = parser.parse_args()

    model = load_model()
    results = []
    for fx in group_stage_fixtures():
        ref = fx.get("referee")
        p = model.predict_match(
            fx["home"], fx["away"], "Group stage",
            competition="World Cup",
            referee=ref,
        )
        ref_norm = _norm_referee(ref) if ref else None
        ref_hist = model.ref_profiles.get(ref_norm) if ref_norm else None
        results.append({
            **fx,
            "referee_in_model": ref is not None and ref in model.ref_profiles,
            "referee_prior_matches": ref_hist.matches if ref_hist else 0,
            "referee_cards_pg": round(ref_hist.cards_pg, 2) if ref_hist else None,
            "expected_gxcxc": round(p["expected_gxcxc"], 1),
            "raw_gxcxc": round(p["raw_gxcxc"], 1),
            "exp_goals": round(p["exp_goals"], 2),
            "exp_corners": round(p["exp_corners"], 1),
            "exp_cards": round(p["exp_cards"], 2),
        })

    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"Wrote {len(results)} predictions → {out}")
    for r in results:
        if r.get("referee"):
            print(
                f"  {r['home']} vs {r['away']}: E[g×c×c]={r['expected_gxcxc']} "
                f"(ref {r['referee']}, {r['referee_prior_matches']} prior games)"
            )


if __name__ == "__main__":
    main()
