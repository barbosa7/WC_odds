"""Fetch international tournament match cards/corners/referees from FBref via soccerdata."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import pandas as pd
from lxml import html

from ml.constants import norm_team

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "wc_data" / "fbref_match_stats.csv"
FBREF_API = "https://fbref.com"
DEFAULT_WC_SEASONS = ("2022", "2018", "2014", "2010")
DEFAULT_EURO_SEASONS = ("2024", "2020", "2016", "2012")
DEFAULT_SEASONS = DEFAULT_WC_SEASONS  # backwards compat

FBREF_ALIASES = {
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Czech Republic": "Czech Republic",
}

REFEREE_ALIASES = {
    "Antonio Matéu": "Antonio Mateu Lahoz",
    "Antonio Matéu Lahoz": "Antonio Mateu Lahoz",
    "Slavko Vinčić": "Slavko Vinčič",
    "Slavko Vincic": "Slavko Vinčič",
}


def norm_fbref_team(name: str) -> str:
    name = str(name).strip()
    name = FBREF_ALIASES.get(name, name)
    return norm_team(name)


def _norm_referee(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name).replace("\xa0", " ")).strip()
    return REFEREE_ALIASES.get(name, REFEREE_ALIASES.get(name.replace("čić", "čič"), name))


def _parse_referee(tree) -> str | None:
    """Extract main referee from scorebox_meta Officials block."""
    text = tree.xpath("string(//div[contains(@class,'scorebox_meta')])")
    if not text:
        return None
    m = re.search(r"Officials:\s*(.+?)(?:Attendance:|Venue:|$)", text, re.S)
    if not m:
        return None
    rm = re.search(r"([^(·]+?)\s*\(Referee\)", m.group(1))
    if not rm:
        return None
    name = _norm_referee(rm.group(1))
    return name or None


def _parse_team_stats_extra(tree) -> dict[str, tuple[int, int]]:
    """Parse home/away values from #team_stats_extra (Corners, Fouls, etc.)."""
    out: dict[str, tuple[int, int]] = {}
    for block in tree.xpath("//div[@id='team_stats_extra']/div"):
        divs = block.xpath("./div")
        i = 0
        while i + 2 < len(divs):
            home_txt = (divs[i].text_content() or "").strip()
            label = (divs[i + 1].text_content() or "").strip()
            away_txt = (divs[i + 2].text_content() or "").strip()
            if label and home_txt.isdigit() and away_txt.isdigit():
                out[label] = (int(home_txt), int(away_txt))
                i += 3
            else:
                i += 1
    return out


def _parse_cards(tree) -> tuple[int, int, int, int]:
    """Return home/away yellow and red card counts from #team_stats."""
    row = tree.xpath(
        "//div[@id='team_stats']//tr[th[normalize-space()='Cards']]/following-sibling::tr[1]"
    )
    if not row:
        return 0, 0, 0, 0
    tds = row[0].xpath("./td")
    if len(tds) < 2:
        return 0, 0, 0, 0

    def count(td, cls: str) -> int:
        return len(td.xpath(f".//span[contains(@class,'{cls}')]"))

    hy = count(tds[0], "yellow_card")
    hr = count(tds[0], "red_card")
    ay = count(tds[1], "yellow_card")
    ar = count(tds[1], "red_card")
    return hy, ay, hr, ar


def parse_match_report(content: bytes | str) -> dict:
    """Extract cards, corners, and referee from a cached FBref match report HTML."""
    if isinstance(content, str):
        content = content.encode("utf-8", errors="replace")
    tree = html.parse(BytesIO(content))
    extra = _parse_team_stats_extra(tree)
    hy, ay, hr, ar = _parse_cards(tree)
    corners = extra.get("Corners", (0, 0))
    fouls = extra.get("Fouls", (0, 0))
    return {
        "home_yellow": hy,
        "away_yellow": ay,
        "home_red": hr,
        "away_red": ar,
        "home_corners": corners[0],
        "away_corners": corners[1],
        "home_fouls": fouls[0],
        "away_fouls": fouls[1],
        "referee": _parse_referee(tree),
    }


def _parse_score(score: str) -> tuple[int | None, int | None, bool, bool]:
    """Return (home, away, went_to_pens, went_to_et) from schedule score string.

    FBref uses formats like ``(4) 3–3 (2)`` for ET + pens — we keep the ET score
    (3–3), not the shootout tally.
    """
    if not score or score in ("", "–", "-"):
        return None, None, False, False
    text = str(score).strip()
    went_to_pens = bool(re.search(r"\(\d+\)\s*\d", text))
    m = re.search(r"(\d+)\s*[–—-]\s*(\d+)", text)
    if not m:
        return None, None, went_to_pens, False
    hs, as_ = int(m.group(1)), int(m.group(2))
    went_to_et = went_to_pens or (hs == as_ and "(" in text)
    return hs, as_, went_to_pens, went_to_et


def add_match_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Add total goals/corners/cards and their product (ET included, pens excluded)."""
    out = df.copy()
    out["total_goals"] = out["home_score"] + out["away_score"]
    out["total_corners"] = out["home_corners"] + out["away_corners"]
    out["total_cards"] = (
        out["home_yellow"] + out["away_yellow"] + out["home_red"] + out["away_red"]
    )
    out["gxcxc"] = out["total_goals"] * out["total_corners"] * out["total_cards"]
    return out


def _fetch_league_stats(
    league: str,
    competition: str,
    seasons: tuple[str, ...] | list[str],
    *,
    force_cache: bool = False,
) -> pd.DataFrame:
    """Download match reports for one FBref international competition."""
    import soccerdata as sd

    rows: list[dict] = []
    seasons = tuple(seasons)
    fb = sd.FBref(leagues=league, seasons=seasons)
    schedule = fb.read_schedule(force_cache=force_cache).reset_index()

    games = schedule[
        schedule["game_id"].notna()
        & schedule["match_report"].notna()
        & (schedule["match_report"].astype(str).str.len() > 0)
    ].copy()

    print(f"  {competition}: {len(games)} matches ({', '.join(seasons)})", flush=True)
    filemask = "match_{}.html"
    for _, game in games.iterrows():
        game_id = str(game["game_id"])
        filepath = fb.data_dir / filemask.format(game_id)
        url = f"{FBREF_API}/en/matches/{game_id}"
        reader = fb.get(url, filepath)
        stats = parse_match_report(reader.read())

        hs, as_, pens, et = _parse_score(game.get("score", ""))
        rows.append(
            {
                "competition": competition,
                "season": int(game["season"]),
                "date": pd.Timestamp(game["date"]).strftime("%Y-%m-%d"),
                "round": game.get("round", ""),
                "home_team": norm_fbref_team(game["home_team"]),
                "away_team": norm_fbref_team(game["away_team"]),
                "home_score": hs,
                "away_score": as_,
                "went_to_pens": pens,
                "went_to_et": et,
                "game_id": game_id,
                "referee": stats.get("referee"),
                **{k: v for k, v in stats.items() if k != "referee"},
            }
        )
        if (len(rows) % 10) == 0:
            print(f"    … {len(rows)}/{len(games)}", flush=True)

    return pd.DataFrame(rows)


def _merge_stats(existing: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        out = new
    else:
        if "competition" not in existing.columns:
            existing = existing.copy()
            existing["competition"] = "World Cup"
        out = (
            pd.concat([existing, new], ignore_index=True)
            .drop_duplicates(subset=["game_id"], keep="last")
        )
    return (
        out.sort_values(["date", "competition"])
        .reset_index(drop=True)
    )


def fetch_world_cup_stats(
    seasons: tuple[str, ...] | list[str] = DEFAULT_WC_SEASONS,
    *,
    force_cache: bool = False,
    merge_existing: bool = True,
) -> pd.DataFrame:
    """Download WC match reports and extract team-level cards/corners."""
    df = _fetch_league_stats(
        "INT-World Cup", "World Cup", tuple(seasons), force_cache=force_cache
    )
    prev = pd.read_csv(OUT_PATH) if merge_existing and OUT_PATH.exists() else None
    return add_match_totals(_merge_stats(prev, df))


def fetch_euro_stats(
    seasons: tuple[str, ...] | list[str] = DEFAULT_EURO_SEASONS,
    *,
    force_cache: bool = False,
    merge_existing: bool = True,
) -> pd.DataFrame:
    """Download European Championship match reports."""
    df = _fetch_league_stats(
        "INT-European Championship",
        "European Championship",
        tuple(seasons),
        force_cache=force_cache,
    )
    prev = pd.read_csv(OUT_PATH) if merge_existing and OUT_PATH.exists() else None
    return add_match_totals(_merge_stats(prev, df))


def fetch_all_tournament_stats(
    *,
    wc_seasons: tuple[str, ...] = DEFAULT_WC_SEASONS,
    euro_seasons: tuple[str, ...] = DEFAULT_EURO_SEASONS,
    force_cache: bool = False,
    merge_existing: bool = True,
) -> pd.DataFrame:
    """Fetch World Cup + European Championship in one run."""
    prev = pd.read_csv(OUT_PATH) if merge_existing and OUT_PATH.exists() else None
    wc = _fetch_league_stats(
        "INT-World Cup", "World Cup", wc_seasons, force_cache=force_cache
    )
    merged = _merge_stats(prev, wc)
    euro = _fetch_league_stats(
        "INT-European Championship",
        "European Championship",
        euro_seasons,
        force_cache=force_cache,
    )
    return add_match_totals(_merge_stats(merged, euro))


def save_match_stats(df: pd.DataFrame, path: Path | None = None) -> Path:
    out = path or OUT_PATH
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    return out


def load_match_stats(path: Path | None = None, *, require_corners: bool = False) -> pd.DataFrame:
    p = path or OUT_PATH
    if not p.exists():
        raise FileNotFoundError(f"Missing {p}. Run: python scripts/fetch_fbref.py")
    df = add_match_totals(pd.read_csv(p, parse_dates=["date"]))
    if "competition" not in df.columns:
        df["competition"] = "World Cup"
    if require_corners:
        df = df[df["total_corners"] > 0].reset_index(drop=True)
    return df


def team_summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-team WC averages for cards and corners (home+away matches)."""
    df = df if df is not None else load_match_stats()
    home = df.assign(
        team=df["home_team"],
        yellow=df["home_yellow"],
        red=df["home_red"],
        corners=df["home_corners"],
        fouls=df["home_fouls"],
    )
    away = df.assign(
        team=df["away_team"],
        yellow=df["away_yellow"],
        red=df["away_red"],
        corners=df["away_corners"],
        fouls=df["away_fouls"],
    )
    long = pd.concat([home, away], ignore_index=True)
    agg = (
        long.groupby("team", as_index=False)
        .agg(
            matches=("team", "count"),
            yellow_pg=("yellow", "mean"),
            red_pg=("red", "mean"),
            corners_pg=("corners", "mean"),
            fouls_pg=("fouls", "mean"),
        )
        .sort_values("corners_pg", ascending=False)
    )
    for col in ("yellow_pg", "red_pg", "corners_pg", "fouls_pg"):
        agg[col] = agg[col].round(2)
    return agg


def backfill_referees_from_cache(
    df: pd.DataFrame | None = None,
    *,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Parse referee names from locally cached FBref match HTML (no network)."""
    import soccerdata as sd

    df = df.copy() if df is not None else pd.read_csv(OUT_PATH)
    if "referee" not in df.columns:
        df["referee"] = pd.NA

    fb = sd.FBref(leagues="INT-World Cup", seasons="2022")
    data_dir = cache_dir or fb.data_dir
    updated = 0
    for i, row in df.iterrows():
        gid = str(row["game_id"])
        path = data_dir / f"match_{gid}.html"
        if not path.exists():
            continue
        ref = parse_match_report(path.read_bytes()).get("referee")
        if ref and (pd.isna(row.get("referee")) or row.get("referee") != ref):
            df.at[i, "referee"] = ref
            updated += 1
    print(f"  Referees parsed/updated: {updated}/{len(df)} matches")
    return df


def referee_summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-referee total match card averages."""
    df = add_match_totals(df if df is not None else load_match_stats())
    df = df[df["referee"].notna()].copy()
    agg = (
        df.groupby("referee", as_index=False)
        .agg(matches=("referee", "count"), cards_pg=("total_cards", "mean"))
        .sort_values("cards_pg", ascending=False)
    )
    agg["cards_pg"] = agg["cards_pg"].round(2)
    return agg
