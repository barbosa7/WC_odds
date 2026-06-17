"""ConnectRPC JSON client for https://api.tychemkt.com."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

import requests

from tyche.types import (
    Contract,
    ContractMark,
    ContractStatus,
    Event,
    EventStatus,
    LeaderboardEntry,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderSide,
    OrderStatus,
    Trade,
    TradeSource,
    User,
    decimal,
    page,
)

DEFAULT_BASE_URL = "https://api.tychemkt.com"


class TycheError(Exception):
    """ConnectRPC error returned by the API."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message}")


class TycheClient:
    """Typed client for AuthService, QueryService, and TradingService."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _call(self, service: str, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/tyche.v1.{service}/{method}"
        resp = self.session.post(
            url,
            json=body or {},
            headers={
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
            },
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise TycheError(
                payload.get("code", "unknown"),
                payload.get("message", resp.reason or "request failed"),
                resp.status_code,
            )
        return payload

    # ------------------------------------------------------------------
    # AuthService
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> User:
        data = self._call("AuthService", "Login", {"email": email, "password": password})
        return _parse_user(data["user"])

    def logout(self) -> None:
        self._call("AuthService", "Logout")

    def get_me(self) -> User:
        data = self._call("AuthService", "GetMe")
        return _parse_user(data["user"])

    # ------------------------------------------------------------------
    # QueryService
    # ------------------------------------------------------------------

    def list_events(
        self,
        *,
        page_size: int = 50,
        page_token: str = "",
        offset: int = 0,
    ) -> tuple[list[Event], str]:
        data = self._call(
            "QueryService",
            "ListEvents",
            {"page": page(page_size=page_size, page_token=page_token, offset=offset)},
        )
        return [_parse_event(e) for e in data.get("events", [])], data.get("nextPageToken", "")

    def get_event(self, event_id: str) -> Event:
        data = self._call("QueryService", "GetEvent", {"eventId": event_id})
        return _parse_event(data["event"])

    def list_contracts(
        self,
        event_id: str,
        *,
        status: ContractStatus | None = None,
        page_size: int = 100,
        page_token: str = "",
    ) -> tuple[list[Contract], str]:
        body: dict[str, Any] = {
            "eventId": event_id,
            "page": page(page_size=page_size, page_token=page_token),
        }
        if status is not None:
            body["status"] = _enum_name(ContractStatus, status, "CONTRACT_STATUS")
        data = self._call("QueryService", "ListContracts", body)
        return [_parse_contract(c) for c in data.get("contracts", [])], data.get("nextPageToken", "")

    def get_contract(self, contract_id: str) -> Contract:
        data = self._call("QueryService", "GetContract", {"contractId": contract_id})
        return _parse_contract(data["contract"])

    def get_order_book(self, contract_id: str) -> OrderBook:
        data = self._call("QueryService", "GetOrderBook", {"contractId": contract_id})
        return _parse_order_book(data["orderBook"])

    def list_orders(
        self,
        *,
        event_id: str = "",
        contract_id: str = "",
        user_id: str = "",
        side: OrderSide | None = None,
        status: OrderStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Order], str]:
        body: dict[str, Any] = {"page": page(page_size=page_size, page_token=page_token)}
        if event_id:
            body["eventId"] = event_id
        if contract_id:
            body["contractId"] = contract_id
        if user_id:
            body["userId"] = user_id
        if side is not None:
            body["side"] = _enum_name(OrderSide, side, "ORDER_SIDE")
        if status is not None:
            body["status"] = _enum_name(OrderStatus, status, "ORDER_STATUS")
        data = self._call("QueryService", "ListOrders", body)
        return [_parse_order(o) for o in data.get("orders", [])], data.get("nextPageToken", "")

    def list_trades(
        self,
        *,
        event_id: str = "",
        contract_id: str = "",
        user_id: str = "",
        source: TradeSource | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Trade], str, int]:
        body: dict[str, Any] = {"page": page(page_size=page_size, page_token=page_token)}
        if event_id:
            body["eventId"] = event_id
        if contract_id:
            body["contractId"] = contract_id
        if user_id:
            body["userId"] = user_id
        if source is not None:
            body["source"] = _enum_name(TradeSource, source, "TRADE_SOURCE")
        data = self._call("QueryService", "ListTrades", body)
        return (
            [_parse_trade(t) for t in data.get("trades", [])],
            data.get("nextPageToken", ""),
            int(data.get("totalCount", 0)),
        )

    def list_contract_marks(self, event_id: str) -> list[ContractMark]:
        data = self._call("QueryService", "ListContractMarks", {"eventId": event_id})
        return [
            ContractMark(contract_id=m["contractId"], price=_dec(m.get("price")))
            for m in data.get("marks", [])
        ]

    def list_positions(
        self,
        *,
        event_id: str = "",
        contract_id: str = "",
        user_id: str = "",
        page_size: int = 200,
        page_token: str = "",
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], str]:
        body: dict[str, Any] = {
            "page": page(page_size=page_size, page_token=page_token, offset=offset),
        }
        if event_id:
            body["eventId"] = event_id
        if contract_id:
            body["contractId"] = contract_id
        if user_id:
            body["userId"] = user_id
        data = self._call("QueryService", "ListPositions", body)
        return data.get("positions", []), data.get("nextPageToken", "")

    def get_leaderboard(self, event_id: str) -> list[LeaderboardEntry]:
        data = self._call("QueryService", "GetLeaderboard", {"eventId": event_id})
        return [
            LeaderboardEntry(
                user_id=e["userId"],
                name=e["name"],
                total_pnl=_dec(e.get("totalPnl")),
                has_unpriced=bool(e.get("hasUnpriced")),
                position_count=int(e.get("positionCount", 0)),
            )
            for e in data.get("entries", [])
        ]

    # ------------------------------------------------------------------
    # TradingService
    # ------------------------------------------------------------------

    def place_order(
        self,
        contract_id: str,
        side: OrderSide,
        limit_price: str | int | float,
        quantity: str | int | float,
    ) -> tuple[Order, list[Trade]]:
        data = self._call(
            "TradingService",
            "PlaceOrder",
            {
                "contractId": contract_id,
                "side": _enum_name(OrderSide, side, "ORDER_SIDE"),
                "limitPrice": decimal(limit_price),
                "quantity": decimal(quantity),
            },
        )
        order = _parse_order(data["order"])
        trades = [_parse_trade(t) for t in data.get("tradesCreated", [])]
        return order, trades

    def cancel_order(self, order_id: str) -> Order:
        data = self._call("TradingService", "CancelOrder", {"orderId": order_id})
        return _parse_order(data["order"])


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------

def _dec(raw: dict[str, Any] | None) -> str:
    if not raw:
        return "0"
    return str(raw.get("value", "0"))


def _enum_name(enum_cls: type, value: IntEnum | int, prefix: str) -> str:
    if isinstance(value, IntEnum):
        name = value.name
    else:
        name = enum_cls(value).name
    return f"{prefix}_{name}"


def _parse_enum(enum_cls: type, raw: Any, prefix: str) -> Any:
    if raw is None:
        return enum_cls(0)
    if isinstance(raw, int):
        return enum_cls(raw)
    if isinstance(raw, str):
        key = raw.removeprefix(prefix + "_")
        return enum_cls[key]
    return enum_cls(0)


def _parse_user(raw: dict[str, Any]) -> User:
    return User(
        id=raw["id"],
        email=raw["email"],
        name=raw["name"],
        is_admin=bool(raw.get("isAdmin")),
        deleted_at=raw.get("deletedAt"),
        created_at=raw.get("createdAt"),
        updated_at=raw.get("updatedAt"),
    )


def _parse_event(raw: dict[str, Any]) -> Event:
    return Event(
        id=raw["id"],
        slug=raw["slug"],
        title=raw["title"],
        description=raw.get("description", ""),
        status=_parse_enum(EventStatus, raw.get("status"), "EVENT_STATUS"),
        created_by=raw.get("createdBy", ""),
        metadata=raw.get("metadata") or {},
        settlement_started_at=raw.get("settlementStartedAt"),
        settlement_started_by=raw.get("settlementStartedBy"),
        settled_at=raw.get("settledAt"),
        settled_by=raw.get("settledBy"),
        created_at=raw.get("createdAt"),
        updated_at=raw.get("updatedAt"),
    )


def _parse_contract(raw: dict[str, Any]) -> Contract:
    return Contract(
        id=raw["id"],
        event_id=raw["eventId"],
        title=raw["title"],
        description=raw.get("description", ""),
        status=_parse_enum(ContractStatus, raw.get("status"), "CONTRACT_STATUS"),
        metadata=raw.get("metadata") or {},
        final_value=_dec(raw.get("finalValue")) if raw.get("finalValue") else None,
        closed_at=raw.get("closedAt"),
        closed_by=raw.get("closedBy"),
        created_at=raw.get("createdAt"),
        updated_at=raw.get("updatedAt"),
    )


def _parse_order_book(raw: dict[str, Any]) -> OrderBook:
    def levels(items: list[dict[str, Any]]) -> list[OrderBookLevel]:
        return [
            OrderBookLevel(
                price=_dec(item.get("price")),
                quantity=_dec(item.get("quantity")),
                order_count=int(item.get("orderCount", 0)),
            )
            for item in items
        ]

    return OrderBook(
        contract_id=raw["contractId"],
        bids=levels(raw.get("bids", [])),
        asks=levels(raw.get("asks", [])),
    )


def _parse_order(raw: dict[str, Any]) -> Order:
    return Order(
        id=raw["id"],
        contract_id=raw["contractId"],
        user_id=raw["userId"],
        side=_parse_enum(OrderSide, raw.get("side"), "ORDER_SIDE"),
        limit_price=_dec(raw.get("limitPrice")),
        original_quantity=_dec(raw.get("originalQuantity")),
        remaining_quantity=_dec(raw.get("remainingQuantity")),
        status=_parse_enum(OrderStatus, raw.get("status"), "ORDER_STATUS"),
        created_at=raw.get("createdAt"),
        cancelled_at=raw.get("cancelledAt"),
    )


def _parse_trade(raw: dict[str, Any]) -> Trade:
    return Trade(
        id=raw["id"],
        contract_id=raw["contractId"],
        buyer_user_id=raw["buyerUserId"],
        seller_user_id=raw["sellerUserId"],
        price=_dec(raw.get("price")),
        quantity=_dec(raw.get("quantity")),
        source=_parse_enum(TradeSource, raw.get("source"), "TRADE_SOURCE"),
        created_by=raw.get("createdBy", ""),
        traded_at=raw.get("tradedAt"),
        created_at=raw.get("createdAt"),
        buy_order_id=raw.get("buyOrderId"),
        sell_order_id=raw.get("sellOrderId"),
        reason=raw.get("reason"),
    )
