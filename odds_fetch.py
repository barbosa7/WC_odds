"""Load betting odds from parsed Oddschecker HTML only — no synthetic fallbacks."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import requests

from parse_oddschecker import parse_all

DATA_DIR = Path(__file__).parent / "wc_data"
ODDS_JSON = DATA_DIR / "odds_oddschecker.json"

ALIASES = {
    "USA": "United States",
    "Czechia": "Czech Republic",
    "Curacao": "Curaçao",
}


def normalise_team(name: str) -> str:
    name = name.strip()
    return ALIASES.get(name, name)


def devig_probs(probs: list[float]) -> list[float]:
    s = sum(probs)
    if s <= 0:
        n = len(probs)
        return [1 / n] * n
    return [p / s for p in probs]


def decimal_to_prob(odds: float) -> float:
    if odds <= 1:
        return 0.0
    return 1.0 / odds


def load_oddschecker_odds() -> dict[str, Any]:
    """Parse HTML exports (refresh JSON cache)."""
    payload = parse_all()
    ODDS_JSON.write_text(json.dumps(payload, indent=2))
    return payload


def get_odds_data() -> dict[str, Any]:
    if ODDS_JSON.exists():
        cached = json.loads(ODDS_JSON.read_text())
        if cached.get("source") == "oddschecker_html":
            return cached
    return load_oddschecker_odds()


def fetch_odds_api(key: str) -> dict[str, float]:
    """Optional live overlay from the-odds-api.com."""
    base = "https://api.the-odds-api.com/v4"
    outright: dict[str, float] = {}
    for sport in ("soccer_fifa_world_cup_winner",):
        url = f"{base}/sports/{sport}/odds"
        params = {
            "apiKey": key,
            "regions": "uk,eu",
            "markets": "outrights",
            "oddsFormat": "decimal",
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code != 200:
                continue
            for event in r.json():
                for book in event.get("bookmakers", []):
                    for market in book.get("markets", []):
                        if market["key"] != "outrights":
                            continue
                        for oc in market.get("outcomes", []):
                            team = normalise_team(oc["name"])
                            price = float(oc["price"])
                            if team not in outright or price < outright[team]:
                                outright[team] = price
        except requests.RequestException:
            pass
    return outright


def strengths_from_outright(outright: dict[str, float]) -> dict[str, float]:
    """Map best available winner odds to relative knockout strength."""
    strengths: dict[str, float] = {}
    for team, odds in outright.items():
        if odds > 1:
            strengths[team] = 1.25 * (1.0 / odds) ** 0.28
    if not strengths:
        return strengths
    floor = min(strengths.values()) * 0.55
    return {t: max(floor, s) for t, s in strengths.items()}


def knockout_match_probs(
    team_a: str,
    team_b: str,
    strengths: dict[str, float],
) -> tuple[float, float, float]:
    """Return (P team_a wins, draw, P team_b wins) from outright-derived strengths."""
    sa, sb = strengths.get(team_a, 1.0), strengths.get(team_b, 1.0)
    diff = sa - sb
    p_a = 1 / (1 + math.exp(-1.15 * diff))
    p_b = 1 / (1 + math.exp(1.15 * diff))
    p_draw = max(0.08, 0.32 - 0.12 * abs(diff))
    s = p_a + p_b + p_draw
    return p_a / s, p_draw / s, p_b / s


def merge_odds() -> dict[str, Any]:
    data = get_odds_data()
    sources = [f"oddschecker:{data.get('winner_html')}", f"oddschecker:{data.get('matches_html')}"]

    outright = {normalise_team(k): float(v) for k, v in data.get("outright", {}).items()}
    group_winner = {
        g: {normalise_team(t): float(o) for t, o in teams.items()}
        for g, teams in data.get("group_winner", {}).items()
    }
    to_qualify = {
        g: {normalise_team(t): float(o) for t, o in teams.items()}
        for g, teams in data.get("to_qualify", {}).items()
    }
    matches = data.get("matches", [])

    key = os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")
    if key:
        api_out = fetch_odds_api(key)
        if api_out:
            sources.append("the-odds-api")
            for team, odds in api_out.items():
                if team not in outright or odds < outright[team]:
                    outright[team] = odds

    strengths = strengths_from_outright(outright)

    # Nudge strengths using group-winner markets (real Oddschecker prices)
    tourn = json.loads((DATA_DIR / "tournament.json").read_text())
    for grp, teams in tourn["groups"].items():
        gw = group_winner.get(grp, {})
        if len(gw) < 2:
            continue
        team_list = [normalise_team(t) for t in teams]
        raw = [decimal_to_prob(gw.get(t, 999)) for t in team_list]
        probs = devig_probs(raw)
        for t, p in zip(team_list, probs):
            base = strengths.get(t, min(strengths.values()) if strengths else 0.35)
            strengths[t] = base * (0.55 + 1.9 * p)

    missing = []
    for teams in tourn["groups"].values():
        for t in teams:
            if t not in outright:
                missing.append(t)

    return {
        "sources": sources,
        "outright": outright,
        "group_winner": group_winner,
        "to_qualify": to_qualify,
        "matches": matches,
        "strengths": strengths,
        "missing_outright": sorted(set(missing)),
    }


def match_lookup(matches: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    """(home, away) -> devigged home/draw/away probabilities."""
    lookup: dict[tuple[str, str], dict[str, float]] = {}
    for m in matches:
        home, away = m["home"], m["away"]
        o = m["odds"]
        ph = decimal_to_prob(o["home"])
        pa = decimal_to_prob(o["away"])
        pd = decimal_to_prob(o.get("draw", 3.3))
        dh, dd, da = devig_probs([ph, pd, pa])
        lookup[(home, away)] = {"home": dh, "draw": dd, "away": da}
    return lookup
