#!/usr/bin/env python3
"""Probe TycheMkt API access and demonstrate the typed client."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tyche import OrderSide, TycheClient, TycheError  # noqa: E402


QUERY_METHODS = [
    "ListEvents",
    "GetEvent",
    "ListContracts",
    "GetContract",
    "ListUsers",
    "ListOrders",
    "GetOrderBook",
    "ListTrades",
    "ListPositions",
    "GetLeaderboard",
    "ListContractMarks",
    "GetEventSettlement",
    "ListSettlementTransfers",
]


def probe_unauthenticated(client: TycheClient) -> None:
    print("=== Unauthenticated probe ===")
    print("Testing QueryService endpoints without a session cookie:\n")
    ok = 0
    for method in QUERY_METHODS:
        try:
            client._call("QueryService", method, {})
            print(f"  {method}: OK (unexpected — endpoint may be public now)")
            ok += 1
        except TycheError as exc:
            print(f"  {method}: HTTP {exc.status_code} — {exc.code}: {exc.message}")
    print(f"\n{ok}/{len(QUERY_METHODS)} endpoints returned data without auth.")
    if ok == 0:
        print("Conclusion: all read endpoints require login. The website gates /markets behind auth too.")


def demo_authenticated(client: TycheClient) -> None:
    email = os.environ.get("TYCHE_EMAIL", "")
    password = os.environ.get("TYCHE_PASSWORD", "")
    if not email or not password:
        print("\nSet TYCHE_EMAIL and TYCHE_PASSWORD to run the authenticated demo.")
        return

    print("\n=== Login ===")
    user = client.login(email, password)
    print(f"Logged in as {user.name} ({user.email})")

    print("\n=== Events + contracts ===")
    events, _ = client.list_events(page_size=10)
    for event in events:
        print(f"  [{event.status.name}] {event.title} ({event.slug})")
        contracts, _ = client.list_contracts(event.id)
        for contract in contracts[:5]:
            print(f"    - {contract.title} [{contract.status.name}]")
        if len(contracts) > 5:
            print(f"    ... +{len(contracts) - 5} more")

    if not events:
        return

    event = events[0]
    contracts, _ = client.list_contracts(event.id)
    if not contracts:
        return

    contract = contracts[0]
    print(f"\n=== Order book: {contract.title} ===")
    book = client.get_order_book(contract.id)
    print(f"  Bids: {len(book.bids)} levels, Asks: {len(book.asks)} levels")
    if book.bids:
        top = book.bids[0]
        print(f"  Best bid: {top.price} x {top.quantity} ({top.order_count} orders)")
    if book.asks:
        top = book.asks[0]
        print(f"  Best ask: {top.price} x {top.quantity} ({top.order_count} orders)")

    marks = client.list_contract_marks(event.id)
    if marks:
        print(f"\n=== Contract marks ({len(marks)}) ===")
        for mark in marks[:5]:
            print(f"  {mark.contract_id}: {mark.price}")

    print("\n=== Trading (examples — not executed) ===")
    print("  # place a limit buy at 45 for qty 10:")
    print('  order, fills = client.place_order(contract.id, OrderSide.BUY, "45", "10")')
    print("  # cancel it:")
    print('  cancelled = client.cancel_order(order.id)')


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe and demo the TycheMkt API client")
    parser.add_argument(
        "--auth-demo",
        action="store_true",
        help="Run authenticated demo (requires TYCHE_EMAIL / TYCHE_PASSWORD)",
    )
    args = parser.parse_args()

    client = TycheClient()
    probe_unauthenticated(client)
    if args.auth_demo:
        demo_authenticated(client)


if __name__ == "__main__":
    main()
