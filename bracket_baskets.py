"""Bracket subtree baskets: theo and joint settlement bounds per knockout node."""

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
QF_KEYS = (97, 98, 99, 100)
SF_KEYS = (101, 102)
QF_PAIRS = ((90, 92), (91, 93), (94, 96), (89, 95))
SF_PAIRS = ((0, 2), (1, 3))

# Rank points when eliminated at each stage (tight min / max within stage)
_ELIM_MIN = {"r32": 5, "r16": 15, "qf": 30, "sf": 40, "final": 70, "win": 90}
_ELIM_MAX = {"r32": 5, "r16": 15, "qf": 30, "sf": 55, "final": 70, "win": 90}

_RANK_SUM_1_32 = sum(overall_rank_points(r) for r in range(1, 33))
_RANK_SUM_1_48 = sum(overall_rank_points(r) for r in range(1, 49))


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


def _group_pts(team: str, results: dict[str, GroupResult]) -> int:
    gr = next(gr for gr in results.values() if team in gr.standings)
    pos = gr.standings.index(team) + 1
    return GROUP_POS_POINTS[pos]


def _group_sum(teams: list[str], results: dict[str, GroupResult]) -> int:
    return sum(_group_pts(t, results) for t in teams)


def _fixed_bounds(teams: list[str], results: dict[str, GroupResult]) -> tuple[int, int] | None:
    """All 48 or all 32 KO teams: rank-point sum is fixed, only bonus varies."""
    n = len(teams)
    if n == 48:
        g = _group_sum(teams, results)
        return g + _RANK_SUM_1_48, g + _RANK_SUM_1_48 + BONUS_GOALS_POINTS
    if n == 32:
        g = _group_sum(teams, results)
        return g + _RANK_SUM_1_32, g + _RANK_SUM_1_32 + BONUS_GOALS_POINTS
    return None


def _settle(team: str, stage: str, results: dict[str, GroupResult], *, for_max: bool, bonus: int) -> int:
    elim = _ELIM_MAX if for_max else _ELIM_MIN
    return _group_pts(team, results) + elim[stage] + bonus


def _resolve(
    key: str | int,
    chain: dict,
    r32_map: dict[int, tuple[str, str]],
    results: dict[str, GroupResult],
    for_max: bool,
) -> list[tuple[dict[str, int], str | None]]:
    """All outcomes for subtree rooted at key. Returns (settled_points, winner)."""
    k = str(key)

    if k.isdigit() and 73 <= int(k) <= 88:
        t1, t2 = r32_map[int(k)]
        out: list[tuple[dict[str, int], str | None]] = []
        for winner, loser in ((t1, t2), (t2, t1)):
            settled = {loser: _settle(loser, "r32", results, for_max=for_max, bonus=0)}
            out.append((settled, winner))
        return out

    if k == "final":
        left_key, right_key = chain["final"]
        combined: list[tuple[dict[str, int], str | None]] = []
        for s_a, w_a in _resolve(left_key, chain, r32_map, results, for_max):
            for s_b, w_b in _resolve(right_key, chain, r32_map, results, for_max):
                if w_a is None or w_b is None:
                    continue
                for win, lose in ((w_a, w_b), (w_b, w_a)):
                    settled = {**s_a, **s_b}
                    bonus = BONUS_GOALS_POINTS if for_max else 0
                    settled[lose] = _settle(lose, "final", results, for_max=for_max, bonus=0)
                    settled[win] = _settle(win, "win", results, for_max=for_max, bonus=bonus)
                    combined.append((settled, win))
        return combined

    if k.isdigit() and int(k) in SF_KEYS:
        left_key, right_key = chain[k]
        combined = []
        for s_a, w_a in _resolve(left_key, chain, r32_map, results, for_max):
            for s_b, w_b in _resolve(right_key, chain, r32_map, results, for_max):
                if w_a is None or w_b is None:
                    continue
                for win, lose in ((w_a, w_b), (w_b, w_a)):
                    settled = {**s_a, **s_b}
                    settled[lose] = _settle(lose, "sf", results, for_max=for_max, bonus=0)
                    combined.append((settled, win))
        return combined

    if k.isdigit() and int(k) in QF_KEYS:
        left_key, right_key = chain[k]
        combined = []
        for s_a, w_a in _resolve(left_key, chain, r32_map, results, for_max):
            for s_b, w_b in _resolve(right_key, chain, r32_map, results, for_max):
                if w_a is None or w_b is None:
                    continue
                for win, lose in ((w_a, w_b), (w_b, w_a)):
                    settled = {**s_a, **s_b}
                    settled[lose] = _settle(lose, "qf", results, for_max=for_max, bonus=0)
                    combined.append((settled, win))
        return combined

    if k.isdigit() and int(k) in R16_IDS:
        left_key, right_key = chain[k]
        combined = []
        for s_a, w_a in _resolve(left_key, chain, r32_map, results, for_max):
            for s_b, w_b in _resolve(right_key, chain, r32_map, results, for_max):
                if w_a is None or w_b is None:
                    continue
                for win, lose in ((w_a, w_b), (w_b, w_a)):
                    settled = {**s_a, **s_b}
                    settled[lose] = _settle(lose, "r16", results, for_max=for_max, bonus=0)
                    combined.append((settled, win))
        return combined

    return []


_POST_WIN_MIN = {"r32": "r16", "r16": "qf", "qf": "sf", "sf": "final"}
_POST_WIN_MAX = "win"


def _stage_after_key(key: str | int) -> str | None:
    k = str(key)
    if k == "final":
        return None
    if k.isdigit() and 73 <= int(k) <= 88:
        return "r32"
    if k.isdigit() and int(k) in R16_IDS:
        return "r16"
    if k.isdigit() and int(k) in QF_KEYS:
        return "qf"
    if k.isdigit() and int(k) in SF_KEYS:
        return "sf"
    return None


def _complete_basket_total(
    settled: dict[str, int],
    winner: str | None,
    root_key: str | int,
    basket: set[str],
    results: dict[str, GroupResult],
    *,
    for_max: bool,
) -> int:
    pts = dict(settled)
    stage_after = _stage_after_key(root_key)
    for team in basket:
        if team in pts:
            continue
        if team == winner and stage_after is not None:
            nxt = _POST_WIN_MAX if for_max else _POST_WIN_MIN[stage_after]
            bonus = BONUS_GOALS_POINTS if for_max and nxt == "win" else 0
            pts[team] = _settle(team, nxt, results, for_max=for_max, bonus=bonus)
        elif team == winner and stage_after is None:
            bonus = BONUS_GOALS_POINTS if for_max else 0
            pts[team] = _settle(team, "win", results, for_max=for_max, bonus=bonus)
        else:
            # Should not happen for valid subtree outcomes
            pts[team] = _group_pts(team, results) + (_ELIM_MAX["win"] if for_max else _ELIM_MIN["r32"])
    return sum(pts[t] for t in basket)


def _joint_bounds(
    teams: list[str],
    root_key: str | int,
    results: dict[str, GroupResult],
    chain: dict,
    r32_map: dict[int, tuple[str, str]],
) -> tuple[int, int]:
    teams = sorted(set(teams))
    fixed = _fixed_bounds(teams, results)
    if fixed:
        return fixed

    basket = set(teams)
    totals_min: list[int] = []
    totals_max: list[int] = []

    for settled, winner in _resolve(root_key, chain, r32_map, results, for_max=False):
        totals_min.append(_complete_basket_total(settled, winner, root_key, basket, results, for_max=False))

    for settled, winner in _resolve(root_key, chain, r32_map, results, for_max=True):
        totals_max.append(_complete_basket_total(settled, winner, root_key, basket, results, for_max=True))

    if not totals_min or not totals_max:
        g = _group_sum(teams, results)
        return g, g + len(teams) * 90

    return min(totals_min), max(totals_max)


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
    chain = tourn["knockout_chain"]

    r32_map: dict[int, tuple[str, str]] = {}
    r32_nodes: dict[int, dict[str, Any]] = {}
    for m in tourn["r32"]:
        home, away = _r32_teams(results, thirds, third_slots, m)
        mid = m["id"]
        r32_map[mid] = (home, away)
        r32_nodes[mid] = {
            "id": f"r32-{mid}",
            "round": "R32",
            "match_id": mid,
            "label": f"{home} vs {away}",
            "teams": [home, away],
        }

    def node_stats(teams: list[str], root_key: str | int) -> dict[str, Any]:
        teams = sorted(set(teams))
        theo = sum(theos.get(t, 0) for t in teams)
        mn, mx = _joint_bounds(teams, root_key, results, chain, r32_map)
        return {
            "teams": teams,
            "team_count": len(teams),
            "theo": round(theo, 2),
            "min_settle": mn,
            "max_settle": mx,
        }

    nodes: list[dict[str, Any]] = []

    r32_by_id = {}
    for mid, raw in r32_nodes.items():
        stats = node_stats(raw["teams"], mid)
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

    r16_by_id = {}
    for rid in R16_IDS:
        a, b = chain[str(rid)]
        teams = r32_by_id[a]["teams"] + r32_by_id[b]["teams"]
        stats = node_stats(teams, rid)
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

    qf_nodes = []
    for i, (a, b) in enumerate(QF_PAIRS):
        ta, tb = r16_by_id[a]["teams"], r16_by_id[b]["teams"]
        stats = node_stats(ta + tb, QF_KEYS[i])
        entry = {
            "id": f"qf-{i}",
            "round": "QF",
            "label": f"QF {i + 1}",
            "children": [f"r16-{a}", f"r16-{b}"],
            **stats,
        }
        qf_nodes.append(entry)
        nodes.append(entry)

    sf_nodes = []
    for i, (a, b) in enumerate(SF_PAIRS):
        ta, tb = qf_nodes[a]["teams"], qf_nodes[b]["teams"]
        stats = node_stats(ta + tb, SF_KEYS[i])
        entry = {
            "id": f"sf-{i}",
            "round": "SF",
            "label": f"Semi-final {i + 1}",
            "children": [qf_nodes[a]["id"], qf_nodes[b]["id"]],
            **stats,
        }
        sf_nodes.append(entry)
        nodes.append(entry)

    stats = node_stats(sf_nodes[0]["teams"] + sf_nodes[1]["teams"], "final")
    final = {
        "id": "final",
        "round": "Final",
        "label": "World Cup Final",
        "children": [sf_nodes[0]["id"], sf_nodes[1]["id"]],
        **stats,
    }
    nodes.append(final)

    all_teams = [t for gr in results.values() for t in gr.standings]
    all_stats = node_stats(all_teams, "final")
    nodes.insert(
        0,
        {
            "id": "all",
            "round": "All",
            "label": "Full tournament (48 teams)",
            **all_stats,
        },
    )

    return {
        "updated": json.loads((completed_path or ROOT / "wc_data" / "completed_matches.json").read_text()).get(
            "updated"
        ),
        "n_matches_completed": len(
            json.loads((completed_path or ROOT / "wc_data" / "completed_matches.json").read_text()).get("matches", [])
        ),
        "third_qualifiers": thirds,
        "theo_source": "expected_points_current.json"
        if (ROOT / "output" / "expected_points_current.json").exists()
        else "expected_points.json",
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
