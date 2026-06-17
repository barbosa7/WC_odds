#!/usr/bin/env python3
"""Fetch TycheMkt orderbooks and compare to Opti WC theos (CLI snapshot writer)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tyche import TycheError  # noqa: E402
from tyche.opportunities import fetch_opportunities  # noqa: E402

OUT = ROOT / "output" / "tychemkt_opportunities.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Tyche orderbooks vs Opti WC theos")
    parser.add_argument("--email", default=os.environ.get("TYCHE_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("TYCHE_PASSWORD", ""))
    parser.add_argument("-o", "--output", type=Path, default=OUT)
    args = parser.parse_args()

    if not args.email or not args.password:
        print("Set TYCHE_EMAIL and TYCHE_PASSWORD, or pass --email / --password")
        sys.exit(1)

    try:
        snapshot = fetch_opportunities(args.email, args.password)
    except TycheError as exc:
        print(f"Tyche API error: {exc}")
        sys.exit(1)

    snapshot["live"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    opps_pre = [i for i in snapshot["items"] if i.get("side_pre")]
    opps_cur = [i for i in snapshot["items"] if i.get("side_current")]
    print(f"Wrote {args.output} ({len(snapshot['items'])} contracts)")
    print(f"  Your open positions: {snapshot['account']['open_positions']}")
    print(f"  Opportunities (pre theo): {len(opps_pre)} buy/sell")
    print(f"  Opportunities (current theo): {len(opps_cur)} buy/sell")


if __name__ == "__main__":
    main()
