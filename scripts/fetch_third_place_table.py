#!/usr/bin/env python3
"""Re-download FIFA third-place combination table from Wikipedia."""

import json
import re
import sys
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "wc_data" / "third_place_combos.json"


def main() -> None:
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": "Template:2026_FIFA_World_Cup_third-place_table",
        "prop": "wikitext",
        "format": "json",
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    wt = r.json()["parse"]["wikitext"]["*"]
    rows = []
    for m in re.finditer(r'scope="row"\s*\|\s*(\d+)\n(.*?)(?=\n\|-\n|\n\|\})', wt, re.S):
        num = int(m.group(1))
        block = m.group(2)
        qual = re.findall(r"'''([A-L])'''", block)
        assigns = re.findall(r"3([A-L])", block)
        if len(qual) == 8 and len(assigns) >= 8:
            rows.append(
                {
                    "id": num,
                    "qualified_groups": sorted(qual),
                    "qualified_key": "".join(sorted(qual)),
                    "third_slots": {
                        "A": assigns[-8],
                        "B": assigns[-7],
                        "D": assigns[-6],
                        "E": assigns[-5],
                        "G": assigns[-4],
                        "I": assigns[-3],
                        "K": assigns[-2],
                        "L": assigns[-1],
                    },
                }
            )
    lookup = {row["qualified_key"]: row["third_slots"] for row in rows}
    OUT.write_text(json.dumps({"combos": rows, "lookup": lookup}, indent=2))
    print(f"Wrote {len(rows)} combinations to {OUT}")


if __name__ == "__main__":
    main()
