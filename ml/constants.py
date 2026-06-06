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


def norm_team(name: str) -> str:
    name = str(name).strip()
    return TEAM_ALIASES.get(name, name)
