"""Bracket subtree baskets: theo and settlement bounds per knockout node."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from simulate import (
    GroupResult,
    _group_standings,
    load_json,
    rank_third_place,
    team_from_ref,
)
from wc_points import BONUS_GOALS_POINTS, GROUP_POS_POINTS, overall_rank_points
from wc_results import load_completed_matches

ROOT = Path(__file__).parent

R16_IDS = (90, 89, 91, 92, 94, 93, 96, 95)
QF_PAIRS = ((90, 92), (91, 93), (94, 96), (89, 95))
SF_PAIRS = ((0, 2), (1, 3))  # indices into qf node list


def _group_state(completed_path: Path | None = None) -> tuple[dict, list[str], dict[str, str]]:
    path = completed_path or ROOT / "wc_data" / "completed_matches.json"
    ctx = load_completed_matches(path)
    tourn = load_json("tournament.json")
    results: dict[str, GroupResult] = {}
    for g, teams in tourn["groups"].items():
        stats = deepcopy(ctx.stats_by_group[g])
        results[g] = GroupResult(standings=_group_standings(teams, stats), stats=stats)
    thirds = rank_third_place(results)
    qkey = "".join(sorted(thirds))
    third_lookup = load_json("third_place_combos.json")["lookup"]
    third_slots = third_lookup.get(qkey)
    if not third_slots:
        third_slots = load_json("third_place_combos.json")["combos"][0]["third_slots"]
    return results, thirds, third_slots


def _r32_teams(results: dict, thirds: list[str], third_slots: dict, match: dict) -> tuple[str, str]:
    from simulate import SimState

    state = SimState(group_results=results, third_qualifiers=thirds)
    home = team_from_ref(match["home"], state, third_slots, match.get("slot"))
    away = (
        team_from_ref("3RD", state, third_slots, match["slot"])
        if match.get("away") == "3RD"
        else team_from_ref(match["away"], state, third_slots, match.get("slot"))
    )
    return home, away


def _ko_bounds(team: str, results: dict, thirds: list[str]) -> tuple[int, int]:
    """Min/max total finish-value points from current group lock + remaining KO path."""
    gr = next(gr for gr in results.values() if team in gr.standings)
    pos = gr.standings.index(team) + 1
    group_pts = GROUP_POS_POINTS[pos]

    qualifies = pos <= 2 or (
        pos == 3 and _group_letter(team, results) in thirds
    )

    if not qualifies:
        rank_pts_min = 5 if _is_last_place(team, results) else 0
        rank_pts_max = rank_pts_min
        bonus_min, bonus_max = 0, BONUS_GOALS_POINTS
        return group_pts + rank_pts_min + bonus_min, group_pts + rank_pts_max + bonus_max

    # Still in R32 — worst: lose R32 (rank 17–32 → 5 pts); best: win tournament
    rank_pts_min = overall_rank_points(32)
    rank_pts_max = overall_rank_points(1)
    bonus_min, bonus_max = 0, BONUS_GOALS_POINTS
    return group_pts + rank_pts_min + bonus_min, group_pts + rank_pts_max + bonus_max


def _group_letter(team: str, results: dict[str, GroupResult]) -> str:
    for g, gr in results.items():
        if team in gr.standings:
            return g
    raise KeyError(team)


def _is_last_place(team: str, results: dict[str, GroupResult]) -> bool:
    """True if team is bottom of their group by our tiebreak (approx 48th overall)."""
    all_fourths = []
    for g, gr in results.items():
        t = gr.standings[3]
        s = gr.stats[t]
        all_fourths.append((t, s["pts"], s["gf"] - s["ga"], s["gf"], g))
    all_fourths.sort(key=lambda x: (x[1], x[2], x[3], x[0]))
    return all_fourths[0][0] == team if all_fourths else False


def _load_theos() -> dict[str, float]:
    path = ROOT / "output" / "expected_points_current.json"
    if not path.exists():
        path = ROOT / "output" / "expected_points.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {row["team"]: float(row["expected_points"]) for row in data.get("teams", [])}


def build_bracket_baskets(completed_path: Path | None = None) -> dict[str, Any]:
    tourn = load_json("tournament.json")
    results, thirds, third_slots = _group_state(completed_path)
    theos = _load_theos()

    r32_nodes: dict[int, dict[str, Any]] = {}
    for m in tourn["r32"]:
        home, away = _r32_teams(results, thirds, third_slots, m)
        mid = m["id"]
        r32_nodes[mid] = {
            "id": f"r32-{mid}",
            "round": "R32",
            "match_id": mid,
            "label": f"{home} vs {away}",
            "teams": [home, away],
            "feeds": tourn["knockout_chain"],
        }

    def node_stats(teams: list[str]) -> dict[str, Any]:
        teams = sorted(set(teams))
        theo = sum(theos.get(t, 0) for t in teams)
        mins, maxs = zip(*(_ko_bounds(t, results, thirds) for t in teams))
        return {
            "teams": teams,
            "team_count": len(teams),
            "theo": round(theo, 2),
            "min_settle": sum(mins),
            "max_settle": sum(maxs),
        }

    nodes: list[dict[str, Any]] = []

    # R32
    r32_by_id = {}
    for mid, raw in r32_nodes.items():
        stats = node_stats(raw["teams"])
        entry = {
            "id": raw["id"],
            "round": "R32",
            "match_id": mid,
            "label": raw["label"],
            "parent_id": _parent_r16(mid, tourn),
            **stats,
        }
        r32_by_id[mid] = entry
        nodes.append(entry)

    # R16
    r16_by_id = {}
    for rid in R16_IDS:
        a, b = tourn["knockout_chain"][str(rid)]
        teams = r32_by_id[a]["teams"] + r32_by_id[b]["teams"]
        stats = node_stats(teams)
        entry = {
            "id": f"r16-{rid}",
            "round": "R16",
            "match_id": rid,
            "label": _pair_label(r32_by_id[a]["label"], r32_by_id[b]["label"]),
            "children": [f"r32-{a}", f"r32-{b}"],
            **stats,
        }
        r16_by_id[rid] = entry
        nodes.append(entry)

    # QF
    qf_nodes = []
    for i, (a, b) in enumerate(QF_PAIRS):
        ta, tb = r16_by_id[a]["teams"], r16_by_id[b]["teams"]
        stats = node_stats(ta + tb)
        entry = {
            "id": f"qf-{i}",
            "round": "QF",
            "label": f"QF {i + 1}",
            "children": [f"r16-{a}", f"r16-{b}"],
            **stats,
        }
        qf_nodes.append(entry)
        nodes.append(entry)

    # SF
    sf_nodes = []
    for i, (a, b) in enumerate(SF_PAIRS):
        ta, tb = qf_nodes[a]["teams"], qf_nodes[b]["teams"]
        stats = node_stats(ta + tb)
        entry = {
            "id": f"sf-{i}",
            "round": "SF",
            "label": f"Semi-final {i + 1}",
            "children": [qf_nodes[a]["id"], qf_nodes[b]["id"]],
            **stats,
        }
        sf_nodes.append(entry)
        nodes.append(entry)

    # Final
    stats = node_stats(sf_nodes[0]["teams"] + sf_nodes[1]["teams"])
    final = {
        "id": "final",
        "round": "Final",
        "label": "World Cup Final",
        "children": [sf_nodes[0]["id"], sf_nodes[1]["id"]],
        **stats,
    }
    nodes.append(final)

    # Full tournament basket (all 48 teams)
    all_teams = [t for gr in results.values() for t in gr.standings]
    stats = node_stats(all_teams)
    nodes.insert(
        0,
        {
            "id": "all",
            "round": "All",
            "label": "Full tournament (48 teams)",
            "teams": sorted(all_teams),
            **stats,
        },
    )

    return {
        "updated": json.loads((completed_path or ROOT / "wc_data" / "completed_matches.json").read_text()).get(
            "updated"
        ),
        "n_matches_completed": len(json.loads((completed_path or ROOT / "wc_data" / "completed_matches.json").read_text()).get("matches", [])),
        "third_qualifiers": thirds,
        "theo_source": "expected_points_current.json" if (ROOT / "output" / "expected_points_current.json").exists() else "expected_points.json",
        "nodes": nodes,
        "r32_order": [m["id"] for m in tourn["r32"]],
    }


def _parent_r16(r32_id: int, tourn: dict) -> str | None:
    for rid, pair in tourn["knockout_chain"].items():
        if rid.isdigit() and int(rid) in R16_IDS and r32_id in pair:
            return f"r16-{rid}"
    return None


def _pair_label(a: str, b: str) -> str:
    return f"Winner({a}) vs Winner({b})"


if __name__ == "__main__":
    payload = build_bracket_baskets()
    out = ROOT / "output" / "bracket_baskets.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(payload['nodes'])} baskets → {out}")
