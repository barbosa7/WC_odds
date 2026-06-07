"""Team aliases and tournament weights."""

from __future__ import annotations

TEAM_ALIASES = {
    "USA": "United States",
    "Korea Republic": "South Korea",
    "Korea, Republic of": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Congo DR": "DR Congo",
    "Congo, DR": "DR Congo",
    "IR Iran": "Iran",
    "Curacao": "Curaçao",
}

RESULT_MAP = {"H": 0, "D": 1, "A": 2}
INV_RESULT = {0: "H", 1: "D", 2: "A"}

TOURNAMENT_WEIGHT = {
    "FIFA World Cup": 1.4,
    "FIFA World Cup qualification": 1.0,
    "UEFA Euro": 1.2,
    "Copa América": 1.1,
    "Copa America": 1.1,
    "African Cup of Nations": 1.0,
    "Friendly": 0.7,
}

# Sample-weight tiers for logistic-regression training (separate from Elo K above).
MAJOR_TOURNAMENTS = frozenset({
    "FIFA World Cup",
    "UEFA Euro",
    "Copa América",
    "Copa America",
    "African Cup of Nations",
    "UEFA Nations League",
    "CONCACAF Nations League",
    "AFC Asian Cup",
    "Gold Cup",
    "Confederations Cup",
})


def tournament_sample_weight(
    tournament: str,
    *,
    wc_weight: float = 4.0,
    major_weight: float = 2.0,
    qual_weight: float = 1.0,
    friendly_weight: float = 0.35,
    other_weight: float = 0.75,
) -> float:
    t = str(tournament or "")
    if t == "FIFA World Cup":
        return wc_weight
    if t in MAJOR_TOURNAMENTS:
        return major_weight
    if "World Cup qualification" in t or "Euro qualification" in t or "qualification" in t.lower():
        return qual_weight
    if t == "Friendly":
        return friendly_weight
    return other_weight


def norm_team(name: str) -> str:
    name = str(name).strip()
    return TEAM_ALIASES.get(name, name)
