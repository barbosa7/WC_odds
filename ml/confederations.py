"""Team → confederation lookup (UEFA, CONMEBOL, …)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.constants import norm_team

CONFEDERATIONS = ("UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC")

# Core nations for 2026 WC + common opponents; seeded from FIFA membership.
_STATIC: dict[str, str] = {
    "Argentina": "CONMEBOL", "Brazil": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL",
    "Chile": "CONMEBOL", "Peru": "CONMEBOL", "Bolivia": "CONMEBOL", "Venezuela": "CONMEBOL",
    "France": "UEFA", "Spain": "UEFA", "England": "UEFA", "Germany": "UEFA",
    "Portugal": "UEFA", "Netherlands": "UEFA", "Belgium": "UEFA", "Croatia": "UEFA",
    "Switzerland": "UEFA", "Denmark": "UEFA", "Italy": "UEFA", "Serbia": "UEFA",
    "Poland": "UEFA", "Ukraine": "UEFA", "Turkey": "UEFA", "Austria": "UEFA",
    "Scotland": "UEFA", "Wales": "UEFA", "Norway": "UEFA", "Sweden": "UEFA",
    "Czech Republic": "UEFA", "Hungary": "UEFA", "Romania": "UEFA", "Slovakia": "UEFA",
    "Slovenia": "UEFA", "Albania": "UEFA", "Greece": "UEFA", "Ireland": "UEFA",
    "Northern Ireland": "UEFA", "Iceland": "UEFA", "Finland": "UEFA", "Bosnia and Herzegovina": "UEFA",
    "Montenegro": "UEFA", "North Macedonia": "UEFA", "Georgia": "UEFA", "Armenia": "UEFA",
    "United States": "CONCACAF", "Mexico": "CONCACAF", "Canada": "CONCACAF",
    "Costa Rica": "CONCACAF", "Panama": "CONCACAF", "Jamaica": "CONCACAF",
    "Honduras": "CONCACAF", "El Salvador": "CONCACAF", "Haiti": "CONCACAF",
    "Trinidad and Tobago": "CONCACAF", "Curaçao": "CONCACAF",
    "Japan": "AFC", "South Korea": "AFC", "Iran": "AFC", "Australia": "AFC",
    "Saudi Arabia": "AFC", "Qatar": "AFC", "Iraq": "AFC", "Uzbekistan": "AFC",
    "Jordan": "AFC", "China": "AFC", "India": "AFC", "Thailand": "AFC",
    "Morocco": "CAF", "Senegal": "CAF", "Nigeria": "CAF", "Egypt": "CAF",
    "Cameroon": "CAF", "Ghana": "CAF", "Algeria": "CAF", "Tunisia": "CAF",
    "Ivory Coast": "CAF", "South Africa": "CAF", "DR Congo": "CAF", "Mali": "CAF",
    "Burkina Faso": "CAF", "Zambia": "CAF", "Angola": "CAF", "Cape Verde": "CAF",
    "New Zealand": "OFC", "Tahiti": "OFC", "Fiji": "OFC",
}


def _seed_from_kaggle() -> dict[str, str]:
    lookup = dict(_STATIC)
    for path in (
        Path(__file__).resolve().parents[1] / "wc_data" / "kaggle_train.csv",
        Path.home() / "Downloads/wc2026-ai-prediction/train.csv",
    ):
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["home_team", "home_conf"])
        for _, row in df.drop_duplicates("home_team").iterrows():
            t = norm_team(row["home_team"])
            if pd.notna(row["home_conf"]) and row["home_conf"]:
                lookup[t] = str(row["home_conf"])
    return lookup


TEAM_CONF = _seed_from_kaggle()


def team_conf(team: str) -> str:
    return TEAM_CONF.get(norm_team(team), "")
