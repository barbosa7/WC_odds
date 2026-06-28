#!/usr/bin/env python3
"""Build bracket subtree basket JSON for the dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bracket_baskets import build_bracket_baskets


def main() -> None:
    payload = build_bracket_baskets()
    out = ROOT / "output" / "bracket_baskets.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(payload['nodes'])} baskets → {out}")


if __name__ == "__main__":
    main()
