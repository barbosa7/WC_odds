"""Parse Oddschecker saved HTML exports into structured odds JSON."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "wc_data"
WINNER_HTML = ROOT / "World Cup Winner Betting Odds _ Football _ Oddschecker.htm"
GS_HTML = ROOT / "World Cup Betting Odds 2026 _ Oddschecker.htm"
OUT = DATA_DIR / "odds_oddschecker.json"

ALIASES = {
    "USA": "United States",
    "Czechia": "Czech Republic",
    "Curacao": "Curaçao",
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Congo DR": "DR Congo",
}


def normalise_team(name: str) -> str:
    name = html.unescape(name.strip())
    return ALIASES.get(name, name)


def extract_hypernova(page: str, key: str) -> dict[str, Any] | None:
    pat = rf'data-hypernova-key="{re.escape(key)}"[^>]*><!--(.*?)-->'
    m = re.search(pat, page, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def _valid_back_odds(data_o: str, decimal: float) -> bool:
    """Skip exchange lay prices and malformed cells."""
    if "/" in data_o:
        return decimal > 1.0
    try:
        o = float(data_o)
    except ValueError:
        return False
    # Exchange lay: data-o="1" with decimal ~2 is not a back price
    if o <= 1.05 and decimal < 10:
        return False
    return o > 1.0


def parse_winner_outright(page: str) -> dict[str, float]:
    """Best decimal outright winner odds per team from odds grid rows."""
    outright: dict[str, float] = {}
    row_pat = re.compile(
        r'<tr class="diff-row evTabRow[^"]*"[^>]*data-bname="([^"]+)"(.*?)</tr>',
        re.S,
    )
    cell_pat = re.compile(
        r'data-o="([^"]*)"[^>]*data-fodds="([0-9.]+)"|data-fodds="([0-9.]+)"[^>]*data-o="([^"]*)"',
        re.S,
    )
    for m in row_pat.finditer(page):
        name = normalise_team(m.group(1))
        row_html = m.group(2)
        prices: list[float] = []
        for cm in cell_pat.finditer(row_html):
            if cm.group(1) is not None:
                data_o, dec = cm.group(1), float(cm.group(2))
            else:
                dec, data_o = float(cm.group(3)), cm.group(4)
            if _valid_back_odds(data_o, dec):
                prices.append(dec)
        if prices:
            outright[name] = min(prices)
    return outright


def parse_group_markets(page: str) -> dict[str, dict[str, float]]:
    """Win Group / To Qualify best decimals from league standings widget."""
    data = extract_hypernova(page, "leaguestandings")
    if not data:
        return {}

    group_winner: dict[str, dict[str, float]] = {}
    to_qualify: dict[str, dict[str, float]] = {}

    for group in data.get("groups", []):
        letter = group["name"].replace("World Cup Group ", "").strip()
        win_market_id = next(
            (m["ocMarketId"] for m in group.get("markets", []) if m["marketName"] == "Win Group"),
            None,
        )
        qual_market_id = next(
            (m["ocMarketId"] for m in group.get("markets", []) if m["marketName"] == "To Qualify"),
            None,
        )
        if win_market_id:
            group_winner[letter] = {}
        if qual_market_id:
            to_qualify[letter] = {}

        for row in group.get("leagueStandings", []):
            team = normalise_team(row["name"])
            best_by_bet = {b["betId"]: b for b in row.get("bestOdds", [])}
            for bet in row.get("bets", []):
                market_id = bet["marketId"]
                best = best_by_bet.get(bet["ocBetId"])
                if not best:
                    continue
                if market_id == win_market_id and letter in group_winner:
                    group_winner[letter][team] = float(best["decimal"])
                elif market_id == qual_market_id and letter in to_qualify:
                    to_qualify[letter][team] = float(best["decimal"])

    return {"group_winner": group_winner, "to_qualify": to_qualify}


def parse_match_odds(page: str) -> list[dict[str, Any]]:
    """All group-stage 1X2 markets (72 matches)."""
    data = extract_hypernova(page, "competitionsworldcupmatches")
    if not data:
        return []

    subevents = data["subevents"]["entities"]
    markets = data["markets"]["entities"]
    bets = data["bets"]["entities"]
    best_odds = data["bestOdds"]["entities"]

    best_by_bet_id = {}
    for entry in best_odds.values():
        best_by_bet_id[entry["betId"]] = entry

    market_by_sub: dict[int, int] = {}
    for m in markets.values():
        if m.get("marketTemplateId") == 1:
            market_by_sub[m["subeventId"]] = m["ocMarketId"]

    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for sid, sub in subevents.items():
        if sub.get("isLive"):
            continue
        home = normalise_team(sub["homeTeamName"])
        away = normalise_team(sub["awayTeamName"])
        date = sub["startTime"][:10]
        key = (home, away, date)
        if key in seen:
            continue
        market_id = market_by_sub.get(int(sid))
        if not market_id:
            continue

        prices: dict[str, float] = {}
        for bet in bets.values():
            if bet["marketId"] != market_id:
                continue
            best = best_by_bet_id.get(bet["ocBetId"])
            if best:
                label = bet["genericName"]
                if label == "HOME":
                    prices["home"] = float(best["decimal"])
                elif label == "AWAY":
                    prices["away"] = float(best["decimal"])
                elif label == "DRAW":
                    prices["draw"] = float(best["decimal"])

        if "home" in prices and "away" in prices:
            seen.add(key)
            matches.append(
                {
                    "home": home,
                    "away": away,
                    "date": date,
                    "odds": prices,
                }
            )

    matches.sort(key=lambda x: (x["date"], x["home"], x["away"]))
    return matches


def parse_all() -> dict[str, Any]:
    if not WINNER_HTML.exists():
        raise FileNotFoundError(f"Missing {WINNER_HTML}")
    if not GS_HTML.exists():
        raise FileNotFoundError(f"Missing {GS_HTML}")

    winner_page = WINNER_HTML.read_text(encoding="utf-8", errors="ignore")
    gs_page = GS_HTML.read_text(encoding="utf-8", errors="ignore")

    groups = parse_group_markets(gs_page)
    payload = {
        "source": "oddschecker_html",
        "winner_html": str(WINNER_HTML.name),
        "matches_html": str(GS_HTML.name),
        "outright": parse_winner_outright(winner_page),
        "group_winner": groups.get("group_winner", {}),
        "to_qualify": groups.get("to_qualify", {}),
        "matches": parse_match_odds(gs_page),
    }
    return payload


def main() -> None:
    payload = parse_all()
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {OUT}")
    print(f"  Outright teams: {len(payload['outright'])}")
    print(f"  Group winner groups: {len(payload['group_winner'])}")
    print(f"  Matches: {len(payload['matches'])}")
    for team in ("Spain", "France", "Portugal", "Argentina"):
        print(f"  {team} winner: {payload['outright'].get(team)}")


if __name__ == "__main__":
    main()
