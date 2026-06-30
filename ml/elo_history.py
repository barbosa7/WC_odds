"""Chronological Elo state for match-event features."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.constants import norm_team
from ml.features import FeatureEngine

ROOT = Path(__file__).resolve().parents[1]
KAGGLE_PATH = ROOT / "wc_data" / "kaggle_train.csv"
INTL_PATH = ROOT / "wc_data" / "international_train.csv"

COMP_TO_TOURNAMENT = {
    "World Cup": "FIFA World Cup",
    "European Championship": "UEFA Euro",
}


def _result_from_scores(hs: float, as_: float) -> str:
    if hs > as_:
        return "H"
    if hs < as_:
        return "A"
    return "D"


def load_international_history() -> pd.DataFrame:
    frames = []
    for path in (KAGGLE_PATH, INTL_PATH):
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["home_team"] = df["home_team"].map(norm_team)
    df["away_team"] = df["away_team"].map(norm_team)
    df = df.dropna(subset=["home_score", "away_score", "result"])
    df = df.sort_values("date").drop_duplicates(
        subset=["date", "home_team", "away_team"], keep="last"
    )
    return df.reset_index(drop=True)


def elo_features(engine: FeatureEngine, home: str, away: str, date, *, neutral: bool = True) -> dict[str, float]:
    """Pre-match Elo comparison features (neutral-site tournaments)."""
    date_str = pd.Timestamp(date).strftime("%Y-%m-%d")
    feats = engine.extract(
        home, away, date_str,
        neutral=neutral,
        tournament="FIFA World Cup",
    )
    diff = feats["elo_diff_raw"]
    return {
        "elo_home": feats["elo_home"],
        "elo_away": feats["elo_away"],
        "elo_diff": diff,
        "abs_elo_diff": abs(diff),
        "elo_avg": 0.5 * (feats["elo_home"] + feats["elo_away"]),
    }


def build_elo_engine(
    before: pd.Timestamp | None = None,
    *,
    intl_df: pd.DataFrame | None = None,
    event_df: pd.DataFrame | None = None,
) -> FeatureEngine:
    """Warm Elo engine on international + prior tournament event matches."""
    engine = FeatureEngine()
    intl = intl_df if intl_df is not None else load_international_history()
    if before is not None:
        intl = intl[intl["date"] < before]

    timeline: list[tuple[pd.Timestamp, str, pd.Series]] = []
    for _, m in intl.iterrows():
        timeline.append((m["date"], "intl", m))
    if event_df is not None:
        ev = event_df.copy()
        ev["date"] = pd.to_datetime(ev["date"])
        if before is not None:
            ev = ev[ev["date"] < before]
        for _, m in ev.iterrows():
            timeline.append((m["date"], "event", m))

    timeline.sort(key=lambda x: (x[0], 0 if x[1] == "intl" else 1))
    for _, kind, m in timeline:
        if kind == "intl":
            engine.update(
                m["home_team"], m["away_team"], m["date"].strftime("%Y-%m-%d"),
                m["result"],
                float(m["home_score"]), float(m["away_score"]),
                neutral=bool(m.get("neutral", False)),
                tournament=str(m.get("tournament", "Friendly")),
            )
        else:
            if pd.isna(m.get("home_score")) or pd.isna(m.get("away_score")):
                continue
            comp = str(m.get("competition", "World Cup"))
            engine.update(
                m["home_team"], m["away_team"], m["date"].strftime("%Y-%m-%d"),
                _result_from_scores(float(m["home_score"]), float(m["away_score"])),
                float(m["home_score"]), float(m["away_score"]),
                neutral=True,
                tournament=COMP_TO_TOURNAMENT.get(comp, comp),
            )
    return engine
