"""Build Tyche orderbook vs model theo comparison snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tyche import TycheClient

ROOT = Path(__file__).resolve().parents[1]

TEAM_ALIASES = {
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Curacao": "Curaçao",
    "USA": "United States",
    "Ivory Coast": "Ivory Coast",
}


def _data_path(name: str) -> Path | None:
    for base in (ROOT / "output", ROOT / "dist" / "data"):
        path = base / name
        if path.exists():
            return path
    return None


def normalise_team(name: str) -> str:
    return TEAM_ALIASES.get(name.strip(), name.strip())


def load_team_theos(filename: str) -> dict[str, float]:
    path = _data_path(filename)
    if not path:
        return {}
    data = json.loads(path.read_text())
    return {row["team"]: float(row["expected_points"]) for row in data.get("teams", [])}


def load_match_theos() -> dict[tuple[str, str], float]:
    path = _data_path("match_events_predictions.json")
    if not path:
        return {}
    rows = json.loads(path.read_text())
    out: dict[tuple[str, str], float] = {}
    for row in rows:
        home = normalise_team(row["home"])
        away = normalise_team(row["away"])
        out[(home, away)] = float(row["expected_gxcxc"])
    return out


def best_bid(levels: list[dict]) -> tuple[float | None, float | None]:
    best_price = None
    best_qty = None
    for level in levels:
        price = float(level["price"]["value"])
        qty = float(level.get("quantity", {}).get("value", "0"))
        if best_price is None or price > best_price:
            best_price, best_qty = price, qty
    return best_price, best_qty


def best_ask(levels: list[dict]) -> tuple[float | None, float | None]:
    best_price = None
    best_qty = None
    for level in levels:
        price = float(level["price"]["value"])
        qty = float(level.get("quantity", {}).get("value", "0"))
        if best_price is None or price < best_price:
            best_price, best_qty = price, qty
    return best_price, best_qty


def compute_edges(theo: float | None, bid: float | None, ask: float | None) -> dict:
    buy_edge = (theo - ask) if theo is not None and ask is not None else None
    sell_edge = (bid - theo) if theo is not None and bid is not None else None

    side = None
    edge = None
    if buy_edge is not None and buy_edge > 0 and (sell_edge is None or sell_edge <= 0 or buy_edge >= sell_edge):
        side = "buy"
        edge = buy_edge
    elif sell_edge is not None and sell_edge > 0:
        side = "sell"
        edge = sell_edge
    elif buy_edge is not None or sell_edge is not None:
        edge = max(v for v in (buy_edge, sell_edge) if v is not None)

    return {
        "buy_edge": round(buy_edge, 2) if buy_edge is not None else None,
        "sell_edge": round(sell_edge, 2) if sell_edge is not None else None,
        "side": side,
        "edge": round(edge, 2) if edge is not None else None,
    }


def load_my_positions(client: TycheClient, event_id: str, user_id: str) -> dict[str, dict]:
    positions, _ = client.list_positions(event_id=event_id, user_id=user_id, page_size=500)
    out: dict[str, dict] = {}
    for row in positions:
        net = float(row["netQuantity"]["value"])
        if net == 0:
            continue
        out[row["contractId"]] = {
            "net": net,
            "cash": float(row.get("cash", {}).get("value", "0")),
            "trade_count": int(row.get("tradeCount", 0)),
        }
    return out


def build_item(
    *,
    kind: str,
    contract: dict,
    theo_pre: float | None,
    theo_current: float | None,
    mark: float | None,
    bid: float | None,
    ask: float | None,
    bid_qty: float | None,
    ask_qty: float | None,
    my_position: dict | None = None,
    extra: dict | None = None,
) -> dict:
    edges_pre = compute_edges(theo_pre, bid, ask)
    edges_current = compute_edges(theo_current, bid, ask)
    item = {
        "kind": kind,
        "contract_id": contract["id"],
        "title": contract["title"],
        "status": contract.get("status", "").removeprefix("CONTRACT_STATUS_"),
        "theo_pre": round(theo_pre, 2) if theo_pre is not None else None,
        "theo_current": round(theo_current, 2) if theo_current is not None else None,
        "mark": round(mark, 2) if mark is not None else None,
        "best_bid": bid,
        "best_ask": ask,
        "bid_qty": bid_qty,
        "ask_qty": ask_qty,
        "buy_edge_pre": edges_pre["buy_edge"],
        "sell_edge_pre": edges_pre["sell_edge"],
        "side_pre": edges_pre["side"],
        "edge_pre": edges_pre["edge"],
        "buy_edge_current": edges_current["buy_edge"],
        "sell_edge_current": edges_current["sell_edge"],
        "side_current": edges_current["side"],
        "edge_current": edges_current["edge"],
        "my_net": my_position["net"] if my_position else 0,
        "my_cash": my_position["cash"] if my_position else 0,
    }
    if extra:
        item.update(extra)
    return item


def fetch_opportunities(email: str, password: str) -> dict:
    theos_pre = load_team_theos("expected_points.json")
    theos_current = load_team_theos("expected_points_current.json")
    match_theos = load_match_theos()

    client = TycheClient()
    user = client.login(email, password)

    events, _ = client.list_events(page_size=10)
    if not events:
        raise RuntimeError("No Tyche events found")

    event = events[0]
    contracts, _ = client.list_contracts(event.id, page_size=500)
    marks_list = client.list_contract_marks(event.id)
    marks = {m.contract_id: float(m.price) for m in marks_list}
    my_positions = load_my_positions(client, event.id, user.id)

    items: list[dict] = []
    for contract in contracts:
        raw = {
            "id": contract.id,
            "title": contract.title,
            "description": contract.description,
            "status": f"CONTRACT_STATUS_{contract.status.name}",
            "metadata": contract.metadata or {},
        }
        meta = contract.metadata or {}
        book = client.get_order_book(contract.id)
        bid, bid_qty = best_bid(
            [{"price": {"value": l.price}, "quantity": {"value": l.quantity}} for l in book.bids]
        )
        ask, ask_qty = best_ask(
            [{"price": {"value": l.price}, "quantity": {"value": l.quantity}} for l in book.asks]
        )
        mark = marks.get(contract.id)

        if meta.get("kind") == "multiplier":
            home = normalise_team(meta.get("homeName", ""))
            away = normalise_team(meta.get("awayName", ""))
            theo = match_theos.get((home, away))
            items.append(
                build_item(
                    kind="match",
                    contract=raw,
                    theo_pre=theo,
                    theo_current=theo,
                    mark=mark,
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    my_position=my_positions.get(contract.id),
                    extra={
                        "home": home,
                        "away": away,
                        "kickoff": meta.get("kickoff"),
                        "stage": meta.get("stage"),
                    },
                )
            )
        elif meta.get("kind") == "total":
            continue
        elif "finish value" in (contract.description or ""):
            team = contract.title
            items.append(
                build_item(
                    kind="team",
                    contract=raw,
                    theo_pre=theos_pre.get(team),
                    theo_current=theos_current.get(team),
                    mark=mark,
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    my_position=my_positions.get(contract.id),
                    extra={"team": team, "group": meta.get("group")},
                )
            )

    ep_pre = _data_path("expected_points.json")
    ep_current = _data_path("expected_points_current.json")
    match_path = _data_path("match_events_predictions.json")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "live": True,
        "account": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "open_positions": len(my_positions),
        },
        "event": {
            "id": event.id,
            "title": event.title,
            "slug": event.slug,
            "status": event.status.name,
        },
        "sources": {
            "theo_pre": str(ep_pre.relative_to(ROOT)) if ep_pre else None,
            "theo_current": str(ep_current.relative_to(ROOT)) if ep_current else None,
            "match_theo": str(match_path.relative_to(ROOT)) if match_path else None,
        },
        "items": items,
    }
