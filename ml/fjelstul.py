"""Fjelstul World Cup database helpers (matchday + referees).

Data: https://github.com/jfjelstul/worldcup (CC-BY-SA 4.0)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.constants import norm_team
from ml.fbref import _norm_referee

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "wc_data" / "fjelstul"

FJELSTUL_ALIASES = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic": "South Korea",
    "USA": "United States",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Czechia": "Czech Republic",
}


def norm_fjelstul_team(name: str) -> str:
    name = str(name).strip()
    name = FJELSTUL_ALIASES.get(name, name)
    return norm_team(name)


def _cluster_matchdays(dates: list[pd.Timestamp]) -> dict[str, int]:
    """Map ISO dates to matchday 1/2/3 by clustering kickoff waves."""
    md_map: dict[str, int] = {}
    md, prev = 1, None
    for d in sorted(dates):
        if prev is not None and (d - prev).days > 2:
            md += 1
        md_map[d.strftime("%Y-%m-%d")] = min(md, 3)
        prev = d
    return md_map


def load_mens_group_matches() -> pd.DataFrame:
    path = DATA_DIR / "matches.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[df["tournament_name"].str.contains("Men", na=False)]
    df = df[(df["group_stage"] == True) | (df["stage_name"].str.lower() == "group stage")]
    df["date"] = pd.to_datetime(df["match_date"])
    df["home"] = df["home_team_name"].map(norm_fjelstul_team)
    df["away"] = df["away_team_name"].map(norm_fjelstul_team)
    df["season"] = df["tournament_name"].str.extract(r"(\d{4})").astype(int)

    rows: list[dict] = []
    for (tid, grp), g in df.groupby(["tournament_id", "group_name"]):
        md_map = _cluster_matchdays([pd.Timestamp(d) for d in g["match_date"].unique()])
        for _, r in g.iterrows():
            ds = pd.Timestamp(r["match_date"]).strftime("%Y-%m-%d")
            rows.append({
                "date_str": ds,
                "home": r["home"],
                "away": r["away"],
                "season": int(r["season"]),
                "group_name": grp,
                "matchday": md_map[ds],
            })
    return pd.DataFrame(rows)


def load_referee_lookup() -> dict[tuple[str, str, str], str]:
    """(date_str, home, away) -> normalised referee name."""
    path = DATA_DIR / "referee_appearances.csv"
    if not path.exists():
        return {}
    ra = pd.read_csv(path)
    m = pd.read_csv(DATA_DIR / "matches.csv")
    m = m[m["tournament_name"].str.contains("Men", na=False)]
    merged = ra.merge(
        m[["match_id", "home_team_name", "away_team_name", "match_date"]],
        on="match_id",
        suffixes=("_ra", "_m"),
    )
    out: dict[tuple[str, str, str], str] = {}
    for _, r in merged.iterrows():
        raw_date = r.get("match_date_m") or r.get("match_date_ra")
        if raw_date is None or (isinstance(raw_date, float) and pd.isna(raw_date)):
            continue
        ds = pd.to_datetime(raw_date).strftime("%Y-%m-%d")
        home = norm_fjelstul_team(r["home_team_name"])
        away = norm_fjelstul_team(r["away_team_name"])
        ref = _norm_referee(f"{r['given_name']} {r['family_name']}".strip())
        out[(ds, home, away)] = ref
    return out


def infer_euro_matchdays(df: pd.DataFrame) -> pd.Series:
    """Infer MD 1/2/3 for Euro group-stage rows without Fjelstul coverage."""
    out = pd.Series(index=df.index, dtype="float")
    euro_gs = df[
        (df["competition"] == "European Championship")
        & (df["round"].astype(str).str.lower().str.contains("group", na=False))
    ]
    for season, g in euro_gs.groupby("season"):
        md_map = _cluster_matchdays([pd.Timestamp(d) for d in g["date"].unique()])
        for idx, r in g.iterrows():
            ds = pd.Timestamp(r["date"]).strftime("%Y-%m-%d")
            out.at[idx] = md_map.get(ds, 2)
    return out


def enrich_match_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Add matchday column and back-fill missing referees from Fjelstul."""
    out = df.copy()
    if "matchday" in out.columns:
        out = out.drop(columns=["matchday"])
    out["date_str"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["matchday"] = pd.NA

    fj = load_mens_group_matches()
    if not fj.empty:
        merged = out.merge(
            fj[["date_str", "home", "away", "matchday"]],
            left_on=["date_str", "home_team", "away_team"],
            right_on=["date_str", "home", "away"],
            how="left",
            suffixes=("", "_fj"),
        )
        if "matchday_fj" in merged.columns:
            merged["matchday"] = merged["matchday_fj"].combine_first(merged["matchday"])
            merged = merged.drop(columns=["matchday_fj"], errors="ignore")
        out = merged.drop(columns=["home", "away"], errors="ignore")

    euro_md = infer_euro_matchdays(out)
    if euro_md.notna().any():
        out.loc[euro_md.notna(), "matchday"] = out.loc[euro_md.notna(), "matchday"].fillna(euro_md)

    ref_lookup = load_referee_lookup()
    if "referee" not in out.columns:
        out["referee"] = pd.NA
    for i, r in out.iterrows():
        if pd.notna(r.get("referee")) and str(r["referee"]).strip():
            continue
        key = (r["date_str"], norm_team(r["home_team"]), norm_team(r["away_team"]))
        if key in ref_lookup:
            out.at[i, "referee"] = ref_lookup[key]

    return out
