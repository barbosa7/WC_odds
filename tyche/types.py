"""Typed message models for the TycheMkt ConnectRPC API (tyche.v1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ContractStatus(IntEnum):
    UNSPECIFIED = 0
    OPEN = 1
    CLOSED = 2


class EventStatus(IntEnum):
    UNSPECIFIED = 0
    OPEN = 1
    SETTLEMENT_OPEN = 2
    SETTLED = 3


class OrderSide(IntEnum):
    UNSPECIFIED = 0
    BUY = 1
    SELL = 2


class OrderStatus(IntEnum):
    UNSPECIFIED = 0
    OPEN = 1
    PARTIALLY_FILLED = 2
    FILLED = 3
    CANCELLED = 4
    CANCELLED_CONTRACT_CLOSED = 5


class TradeSource(IntEnum):
    UNSPECIFIED = 0
    ORDERBOOK = 1
    MANUAL = 2
    CORRECTION = 3


def decimal(value: str | int | float) -> dict[str, str]:
    """Build a protobuf Decimal for JSON requests."""
    return {"value": str(value)}


def page(*, page_size: int = 50, page_token: str = "", offset: int = 0) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if page_size:
        body["pageSize"] = page_size
    if page_token:
        body["pageToken"] = page_token
    if offset:
        body["offset"] = offset
    return body


@dataclass
class User:
    id: str
    email: str
    name: str
    is_admin: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class UserProfile:
    id: str
    name: str


@dataclass
class Event:
    id: str
    slug: str
    title: str
    description: str
    status: EventStatus
    created_by: str
    metadata: dict[str, Any] = field(default_factory=dict)
    settlement_started_at: str | None = None
    settlement_started_by: str | None = None
    settled_at: str | None = None
    settled_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Contract:
    id: str
    event_id: str
    title: str
    description: str
    status: ContractStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    final_value: str | None = None
    closed_at: str | None = None
    closed_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class OrderBookLevel:
    price: str
    quantity: str
    order_count: int


@dataclass
class OrderBook:
    contract_id: str
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)


@dataclass
class Order:
    id: str
    contract_id: str
    user_id: str
    side: OrderSide
    limit_price: str
    original_quantity: str
    remaining_quantity: str
    status: OrderStatus
    created_at: str | None = None
    cancelled_at: str | None = None


@dataclass
class Trade:
    id: str
    contract_id: str
    buyer_user_id: str
    seller_user_id: str
    price: str
    quantity: str
    source: TradeSource
    created_by: str
    traded_at: str | None = None
    created_at: str | None = None
    buy_order_id: str | None = None
    sell_order_id: str | None = None
    reason: str | None = None


@dataclass
class ContractMark:
    contract_id: str
    price: str


@dataclass
class LeaderboardEntry:
    user_id: str
    name: str
    total_pnl: str
    has_unpriced: bool
    position_count: int
