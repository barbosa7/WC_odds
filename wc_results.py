"""Load and validate completed group-stage match results."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ml.constants import norm_team

DATA_DIR = Path(__file__).parent / "wc_data"


@dataclass
class CompletedMatch:
    home: str
    away: str
    home_score: int
    away_score: int
    group: str
    matchday: int  # 1-based


@dataclass
class ConditionalContext:
    """State derived from real group-stage results already played."""

    matches: list[CompletedMatch] = field(default_factory=list)
    played: dict[str, set[tuple[int, int, int]]] = field(default_factory=dict)
    stats_by_group: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    engine_sequence: list[tuple[str, str, int, int]] = field(default_factory=list)


def build_fixture_index(
    tourn: dict[str, Any],
) -> dict[tuple[str, str], tuple[str, int, int, int]]:
    """Map (schedule home, schedule away) → (group, md_idx, i, j)."""
    index: dict[tuple[str, str], tuple[str, int, int, int]] = {}
    for group, teams in tourn["groups"].items():
        for md_idx, md in enumerate(tourn["group_matchdays"]):
            for i, j in md:
                home = norm_team(teams[i])
                away = norm_team(teams[j])
                index[(home, away)] = (group, md_idx, i, j)
    return index


def apply_fixture_to_stats(
    stats: dict[str, dict[str, int]],
    team_a: str,
    team_b: str,
    gf_a: int,
    gf_b: int,
) -> None:
    stats[team_a]["gf"] += gf_a
    stats[team_a]["ga"] += gf_b
    stats[team_b]["gf"] += gf_b
    stats[team_b]["ga"] += gf_a
    if gf_a > gf_b:
        stats[team_a]["pts"] += 3
    elif gf_b > gf_a:
        stats[team_b]["pts"] += 3
    else:
        stats[team_a]["pts"] += 1
        stats[team_b]["pts"] += 1


def load_tournament() -> dict[str, Any]:
    return json.loads((DATA_DIR / "tournament.json").read_text())


def load_completed_matches(path: Path, tourn: dict[str, Any] | None = None) -> ConditionalContext:
    """Parse completed match JSON and build conditional simulation state."""
    if tourn is None:
        tourn = load_tournament()

    raw = json.loads(path.read_text())
    entries = raw.get("matches", raw if isinstance(raw, list) else [])
    if not entries:
        raise ValueError(f"No completed matches in {path}")

    index = build_fixture_index(tourn)
    all_teams = {norm_team(t) for teams in tourn["groups"].values() for t in teams}

    stats_by_group: dict[str, dict[str, dict[str, int]]] = {
        g: {t: {"gf": 0, "ga": 0, "pts": 0} for t in teams}
        for g, teams in tourn["groups"].items()
    }
    played: dict[str, set[tuple[int, int, int]]] = {g: set() for g in tourn["groups"]}
    resolved: list[tuple[CompletedMatch, str, str, int, int, int, int, int]] = []
    seen: set[tuple[str, str, str, int, int, int]] = set()

    for idx, entry in enumerate(entries, start=1):
        user_home = norm_team(entry["home"])
        user_away = norm_team(entry["away"])
        hs = int(entry["home_score"])
        as_ = int(entry["away_score"])
        if hs < 0 or as_ < 0:
            raise ValueError(f"Match {idx}: scores must be non-negative")

        fixture = index.get((user_home, user_away)) or index.get((user_away, user_home))
        if fixture is None:
            raise ValueError(
                f"Match {idx}: {entry['home']} vs {entry['away']} is not a group-stage fixture"
            )

        group, md_idx, i, j = fixture
        sched_home = norm_team(tourn["groups"][group][i])
        sched_away = norm_team(tourn["groups"][group][j])

        if user_home == sched_home:
            gf_home, gf_away = hs, as_
        else:
            gf_home, gf_away = as_, hs

        key = (group, md_idx, i, j)
        if key in seen:
            raise ValueError(
                f"Duplicate result for {sched_home} vs {sched_away} (matchday {md_idx + 1})"
            )
        seen.add(key)

        if entry.get("group") and entry["group"].upper() != group:
            raise ValueError(
                f"Match {idx}: group {entry['group']} does not match fixture group {group}"
            )
        if entry.get("matchday") and int(entry["matchday"]) != md_idx + 1:
            raise ValueError(
                f"Match {idx}: matchday {entry['matchday']} does not match fixture matchday {md_idx + 1}"
            )

        if sched_home not in all_teams or sched_away not in all_teams:
            raise ValueError(f"Match {idx}: unknown team in fixture")

        apply_fixture_to_stats(stats_by_group[group], sched_home, sched_away, gf_home, gf_away)
        played[group].add((md_idx, i, j))
        resolved.append(
            (CompletedMatch(sched_home, sched_away, gf_home, gf_away, group, md_idx + 1),
             sched_home, sched_away, gf_home, gf_away, group, md_idx, i, j)
        )

    resolved.sort(key=lambda x: (x[6], x[5], x[7], x[8]))
    matches = [r[0] for r in resolved]
    engine_sequence = [(r[1], r[2], r[3], r[4]) for r in resolved]

    return ConditionalContext(
        matches=matches,
        played=played,
        stats_by_group=stats_by_group,
        engine_sequence=engine_sequence,
    )


def group_stats_copy(ctx: ConditionalContext, group: str, teams: list[str]) -> dict[str, dict[str, int]]:
    """Deep copy of accumulated stats for one group (or empty if none played)."""
    if group in ctx.stats_by_group:
        return deepcopy(ctx.stats_by_group[group])
    return {t: {"gf": 0, "ga": 0, "pts": 0} for t in teams}


def seed_ml_engine(engine, ctx: ConditionalContext) -> None:
    """Apply completed match outcomes to the ML feature engine."""
    from ml.predictor import WC_START, WC_TOURNAMENT

    for home, away, gh, ga in ctx.engine_sequence:
        if gh > ga:
            res = "H"
        elif ga > gh:
            res = "A"
        else:
            res = "D"
        engine.update(home, away, WC_START, res, gh, ga, neutral=True, tournament=WC_TOURNAMENT)


def completed_matches_summary(ctx: ConditionalContext) -> list[dict[str, Any]]:
    return [
        {
            "home": m.home,
            "away": m.away,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "group": m.group,
            "matchday": m.matchday,
        }
        for m in ctx.matches
    ]
