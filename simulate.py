"""Monte Carlo World Cup simulation with custom scoring."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from odds_fetch import match_lookup, merge_odds
from wc_points import (
    BONUS_GOALS_POINTS,
    GROUP_POS_POINTS,
    STAGE_ORDER,
    overall_rank_points,
    stage_from_rank,
)

DATA_DIR = Path(__file__).parent / "wc_data"


@dataclass
class GroupResult:
    standings: list[str]
    stats: dict[str, dict[str, int]]


@dataclass
class SimState:
    group_results: dict[str, GroupResult] = field(default_factory=dict)
    third_qualifiers: list[str] = field(default_factory=list)
    r32_winners: dict[int, str] = field(default_factory=dict)


def load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text())


def play_match(
    team_a: str,
    team_b: str,
    strengths: dict[str, float],
    rng: random.Random,
) -> tuple[str, str]:
    """Return (winner, loser)."""
    sa, sb = strengths.get(team_a, 1.0), strengths.get(team_b, 1.0)
    diff = sa - sb
    p_a = 1 / (1 + np.exp(-1.15 * diff))
    p_b = 1 / (1 + np.exp(1.15 * diff))
    p_draw = max(0.08, 0.32 - 0.12 * abs(diff))
    s = p_a + p_b + p_draw
    p_a, p_draw, p_b = p_a / s, p_draw / s, p_b / s
    u = rng.random()
    if u < p_a:
        return team_a, team_b
    if u < p_a + p_draw:
        return (team_a, team_b) if rng.random() < p_a / (p_a + p_b) else (team_b, team_a)
    return team_b, team_a


def resolve_match_probs(
    team_a: str,
    team_b: str,
    lookup: dict[tuple[str, str], dict[str, float]],
) -> tuple[float, float, float]:
    """Return (P team_a wins, draw, P team_b wins) using Oddschecker 1X2 prices."""
    if (team_a, team_b) in lookup:
        p = lookup[(team_a, team_b)]
        return p["home"], p["draw"], p["away"]
    if (team_b, team_a) in lookup:
        p = lookup[(team_b, team_a)]
        return p["away"], p["draw"], p["home"]
    raise KeyError(f"No Oddschecker odds for {team_a} vs {team_b}")


def simulate_match_result(
    team_a: str,
    team_b: str,
    lookup: dict[tuple[str, str], dict[str, float]],
    rng: random.Random,
) -> tuple[int, int]:
    """Simulate goals for team_a vs team_b from market 1X2 probabilities."""
    pa, pd, pb = resolve_match_probs(team_a, team_b, lookup)
    u = rng.random()
    if u < pa:
        ga = rng.randint(1, 3)
        gb = rng.randint(0, ga - 1)
        return ga, gb
    if u < pa + pd:
        g = rng.randint(1, 3)
        return g, g
    gb = rng.randint(1, 3)
    ga = rng.randint(0, gb - 1)
    return ga, gb


def simulate_group(
    teams: list[str],
    rng: random.Random,
    matchdays: list[list[list[int]]],
    lookup: dict[tuple[str, str], dict[str, float]],
) -> GroupResult:
    stats = {t: {"gf": 0, "ga": 0, "pts": 0} for t in teams}
    for md in matchdays:
        for i, j in md:
            a, b = teams[i], teams[j]
            gf_a, gf_b = simulate_match_result(a, b, lookup, rng)
            stats[a]["gf"] += gf_a
            stats[a]["ga"] += gf_b
            stats[b]["gf"] += gf_b
            stats[b]["ga"] += gf_a
            if gf_a > gf_b:
                stats[a]["pts"] += 3
            elif gf_b > gf_a:
                stats[b]["pts"] += 3
            else:
                stats[a]["pts"] += 1
                stats[b]["pts"] += 1

    standings = sorted(
        teams,
        key=lambda t: (
            -stats[t]["pts"],
            -(stats[t]["gf"] - stats[t]["ga"]),
            -stats[t]["gf"],
            t,
        ),
    )
    return GroupResult(standings=standings, stats=stats)


def rank_third_place(group_results: dict[str, GroupResult]) -> list[str]:
    thirds = []
    for g, gr in group_results.items():
        t = gr.standings[2]
        s = gr.stats[t]
        thirds.append((g, s["pts"], s["gf"] - s["ga"], s["gf"]))
    thirds.sort(key=lambda x: (-x[1], -x[2], -x[3], x[0]))
    return [g for g, *_ in thirds[:8]]


def team_from_ref(
    ref: str,
    state: SimState,
    third_slots: dict[str, str],
    slot: str | None = None,
) -> str:
    if ref == "3RD":
        grp = third_slots[slot]
        ref = f"3{grp}"
    pos = int(ref[0])
    grp = ref[1]
    gr = state.group_results[grp]
    if pos <= 2:
        return gr.standings[pos - 1]
    if pos == 3:
        if grp not in state.third_qualifiers:
            raise RuntimeError(f"3rd from {grp} not in qualifiers")
        return gr.standings[2]
    return gr.standings[3]


def play_knockout_round(
    pairs: list[tuple[str, str]],
    strengths: dict[str, float],
    rng: random.Random,
) -> tuple[list[str], list[str]]:
    winners, losers = [], []
    for a, b in pairs:
        w, l = play_match(a, b, strengths, rng)
        winners.append(w)
        losers.append(l)
    return winners, losers


def run_single_sim(
    strengths: dict[str, float],
    lookup: dict[tuple[str, str], dict[str, float]],
    rng: random.Random,
) -> dict[str, Any]:
    tourn = load_json("tournament.json")
    third_lookup = load_json("third_place_combos.json")["lookup"]
    state = SimState()

    for g, teams in tourn["groups"].items():
        state.group_results[g] = simulate_group(
            teams, rng, tourn["group_matchdays"], lookup
        )

    state.third_qualifiers = rank_third_place(state.group_results)
    qkey = "".join(sorted(state.third_qualifiers))
    third_slots = third_lookup.get(qkey)
    if not third_slots:
        third_slots = load_json("third_place_combos.json")["combos"][0]["third_slots"]

    r32_pairs = []
    for m in tourn["r32"]:
        home = team_from_ref(m["home"], state, third_slots, m.get("slot"))
        away = (
            team_from_ref("3RD", state, third_slots, m["slot"])
            if m["away"] == "3RD"
            else team_from_ref(m["away"], state, third_slots, m.get("slot"))
        )
        r32_pairs.append((home, away))

    r32_w, r32_l = play_knockout_round(r32_pairs, strengths, rng)
    w = {m["id"]: r32_w[i] for i, m in enumerate(tourn["r32"])}

    def pair(mid: int) -> tuple[str, str]:
        a, b = tourn["knockout_chain"][str(mid)]
        return w[a], w[b]

    r16_pairs = [pair(mid) for mid in (90, 89, 91, 92, 94, 93, 96, 95)]
    r16_w, r16_l = play_knockout_round(r16_pairs, strengths, rng)
    w16 = dict(zip((90, 89, 91, 92, 94, 93, 96, 95), r16_w))

    qf_pairs = [(w16[90], w16[92]), (w16[91], w16[93]), (w16[94], w16[96]), (w16[89], w16[95])]
    qf_w, qf_l = play_knockout_round(qf_pairs, strengths, rng)

    sf_pairs = [(qf_w[0], qf_w[2]), (qf_w[1], qf_w[3])]
    sf_w, sf_l = play_knockout_round(sf_pairs, strengths, rng)

    final_w, final_l = play_match(sf_w[0], sf_w[1], strengths, rng)
    bronze_w, bronze_l = play_match(sf_l[0], sf_l[1], strengths, rng)

    ranks: dict[str, int] = {}
    ranks[final_w] = 1
    ranks[final_l] = 2
    ranks[bronze_w] = 3
    ranks[bronze_l] = 4
    for i, t in enumerate(qf_l):
        ranks[t] = 5 + i
    for i, t in enumerate(r16_l):
        ranks[t] = 9 + i
    for i, t in enumerate(r32_l):
        ranks[t] = 17 + i

    all_teams = [t for gr in state.group_results.values() for t in gr.standings]
    remaining = [t for t in all_teams if t not in ranks]
    rem_stats = []
    for gr in state.group_results.values():
        for t in remaining:
            if t not in gr.standings:
                continue
            s = gr.stats[t]
            pos = gr.standings.index(t) + 1
            rem_stats.append((t, s["pts"], s["gf"] - s["ga"], s["gf"] + s["ga"], pos))
    rem_stats.sort(key=lambda x: (-x[1], -x[2], -x[3], x[4], x[0]))
    for i, (t, *_) in enumerate(rem_stats):
        ranks[t] = 33 + i

    goals_sum = {
        t: s["gf"] + s["ga"]
        for gr in state.group_results.values()
        for t, s in gr.stats.items()
    }
    max_g = max(goals_sum.values())
    bonus_teams = [t for t, v in goals_sum.items() if v == max_g]

    points: dict[str, float] = defaultdict(float)
    stage_hit: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    group_pos_hit: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for gr in state.group_results.values():
        for pos, team in enumerate(gr.standings, start=1):
            points[team] += GROUP_POS_POINTS[pos]
            group_pos_hit[team][pos] += 1

    for team, rank in ranks.items():
        points[team] += overall_rank_points(rank)
        stage_hit[team][stage_from_rank(rank)] += 1

    for team in bonus_teams:
        points[team] += BONUS_GOALS_POINTS / len(bonus_teams)

    return {
        "points": dict(points),
        "group_pos": {t: dict(v) for t, v in group_pos_hit.items()},
        "stages": {t: dict(v) for t, v in stage_hit.items()},
        "bonus_teams": bonus_teams,
    }


def run_monte_carlo(n_sims: int = 25_000, seed: int = 42) -> dict[str, Any]:
    odds = merge_odds()
    strengths = odds["strengths"]
    lookup = match_lookup(odds["matches"])
    rng = random.Random(seed)

    all_teams = []
    for teams in load_json("tournament.json")["groups"].values():
        all_teams.extend(teams)

    acc_points = defaultdict(float)
    acc_group = defaultdict(lambda: defaultdict(float))
    acc_stage = defaultdict(lambda: defaultdict(float))
    acc_bonus = defaultdict(float)

    for _ in range(n_sims):
        res = run_single_sim(strengths, lookup, rng)
        for t, p in res["points"].items():
            acc_points[t] += p
        for t, pos_d in res["group_pos"].items():
            for pos, c in pos_d.items():
                acc_group[t][pos] += c
        for t, st_d in res["stages"].items():
            for st, c in st_d.items():
                acc_stage[t][st] += c
        for t in res["bonus_teams"]:
            acc_bonus[t] += 1 / len(res["bonus_teams"])

    n = n_sims
    results = []
    for team in sorted(all_teams, key=lambda t: -acc_points[t]):
        gp = {k: acc_group[team][k] / n for k in range(1, 5)}
        stages = {k: acc_stage[team][k] / n for k in acc_stage[team]}
        p_r32 = sum(stages.get(s, 0) for s in STAGE_ORDER[2:])
        p_r16 = sum(stages.get(s, 0) for s in STAGE_ORDER[3:])
        p_qf = sum(stages.get(s, 0) for s in STAGE_ORDER[4:])
        p_sf = sum(
            stages.get(s, 0)
            for s in ("Fourth", "Third place", "Runner-up", "Champion")
        )
        results.append(
            {
                "team": team,
                "expected_points": round(acc_points[team] / n, 2),
                "p_bonus_goals": round(acc_bonus[team] / n, 4),
                "p_group_1": round(gp.get(1, 0), 4),
                "p_group_2": round(gp.get(2, 0), 4),
                "p_group_3": round(gp.get(3, 0), 4),
                "p_group_4": round(gp.get(4, 0), 4),
                "p_round_of_32": round(p_r32, 4),
                "p_round_of_16": round(p_r16, 4),
                "p_quarter_final": round(p_qf, 4),
                "p_semi_final": round(p_sf, 4),
                "p_third_place": round(stages.get("Third place", 0), 4),
                "p_runner_up": round(stages.get("Runner-up", 0), 4),
                "p_champion": round(stages.get("Champion", 0), 4),
                "stage_probs": {k: round(v, 4) for k, v in sorted(stages.items())},
            }
        )

    return {
        "n_simulations": n_sims,
        "odds_sources": odds["sources"],
        "missing_outright": odds.get("missing_outright", []),
        "outright_input": odds["outright"],
        "teams": results,
    }
