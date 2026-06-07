"""Fetch and convert martj42 international results → training CSV."""

from __future__ import annotations

import io
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

from ml.confederations import team_conf
from ml.constants import norm_team

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "wc_data"
RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
FORMER_NAMES_URL = "https://raw.githubusercontent.com/martj42/international_results/master/former_names.csv"
OUT_PATH = DATA_DIR / "international_train.csv"
EXTENDED_PATH = DATA_DIR / "international_train_extended.csv"
KAGGLE_PATH = DATA_DIR / "kaggle_train.csv"

MIN_DATE = "1993-01-01"


def _fetch(url: str) -> str:
    with urlopen(url, timeout=120) as resp:
        return resp.read().decode("utf-8")


def _load_former_names() -> dict[str, str]:
    """Map historical names → current martj42 name."""
    try:
        raw = _fetch(FORMER_NAMES_URL)
    except OSError:
        return {}
    df = pd.read_csv(io.StringIO(raw))
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        current = str(row["current"]).strip()
        former = str(row["former"]).strip()
        mapping[former] = current
    return mapping


def _result(h: float, a: float) -> str:
    if h > a:
        return "H"
    if a > h:
        return "A"
    return "D"


def fetch_and_convert(*, min_date: str = MIN_DATE, out_path: Path | None = None) -> Path:
    out = out_path or OUT_PATH
    DATA_DIR.mkdir(exist_ok=True)

    raw = _fetch(RESULTS_URL)
    df = pd.read_csv(io.StringIO(raw), parse_dates=["date"])
    former = _load_former_names()

    df = df[df["date"] >= pd.Timestamp(min_date)].copy()
    df["home_team"] = df["home_team"].map(lambda t: former.get(str(t).strip(), str(t).strip()))
    df["away_team"] = df["away_team"].map(lambda t: former.get(str(t).strip(), str(t).strip()))
    df["home_team"] = df["home_team"].map(norm_team)
    df["away_team"] = df["away_team"].map(norm_team)

    df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
    df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
    df = df.dropna(subset=["home_score", "away_score"])
    df["result"] = [_result(h, a) for h, a in zip(df["home_score"], df["away_score"])]

    neutral = df["neutral"].astype(str).str.lower().isin(("true", "1", "t", "yes"))
    df["neutral"] = neutral
    df["home_conf"] = df["home_team"].map(team_conf)
    df["away_conf"] = df["away_team"].map(team_conf)
    df = df.sort_values("date").reset_index(drop=True)
    df.insert(0, "match_id", range(1, len(df) + 1))

    out_df = df[
        [
            "match_id", "date", "home_team", "away_team",
            "home_score", "away_score", "tournament", "neutral",
            "home_conf", "away_conf", "result",
        ]
    ]
    out_df.to_csv(out, index=False)
    return out


def load_train(path: Path | None = None) -> pd.DataFrame:
    p = path or OUT_PATH
    if not p.exists():
        fetch_and_convert(out_path=p)
    df = pd.read_csv(p, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def build_extended_train() -> pd.DataFrame:
    """Kaggle curated history + martj42 updates after Kaggle cutoff."""
    mart = load_train()
    kaggle_path = KAGGLE_PATH
    if not kaggle_path.exists():
        kaggle_path = Path.home() / "Downloads/wc2026-ai-prediction/train.csv"
    if not kaggle_path.exists():
        return mart
    kaggle = pd.read_csv(kaggle_path, parse_dates=["date"]).sort_values("date")
    cutoff = kaggle["date"].max()
    updates = mart[mart["date"] > cutoff].copy()
    combined = pd.concat([kaggle, updates], ignore_index=True).sort_values("date")
    combined = combined.reset_index(drop=True)
    combined["match_id"] = range(1, len(combined) + 1)
    combined.to_csv(EXTENDED_PATH, index=False)
    return combined


def load_extended_train() -> pd.DataFrame:
    if EXTENDED_PATH.exists():
        return pd.read_csv(EXTENDED_PATH, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    return build_extended_train()
