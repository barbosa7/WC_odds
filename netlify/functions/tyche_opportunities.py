"""Live Tyche orderbook + positions API for the dashboard."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tyche import TycheError  # noqa: E402
from tyche.opportunities import fetch_opportunities  # noqa: E402

JSON_HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "private, no-store",
}


def handler(event, context):
    if event.get("httpMethod") not in (None, "GET"):
        return {
            "statusCode": 405,
            "headers": JSON_HEADERS,
            "body": json.dumps({"error": "Method not allowed"}),
        }

    email = os.environ.get("TYCHE_EMAIL", "")
    password = os.environ.get("TYCHE_PASSWORD", "")
    if not email or not password:
        return {
            "statusCode": 503,
            "headers": JSON_HEADERS,
            "body": json.dumps({
                "error": "Tyche credentials not configured",
                "hint": "Set TYCHE_EMAIL and TYCHE_PASSWORD in Netlify environment variables",
            }),
        }

    try:
        data = fetch_opportunities(email, password)
        return {
            "statusCode": 200,
            "headers": JSON_HEADERS,
            "body": json.dumps(data),
        }
    except TycheError as exc:
        return {
            "statusCode": 502,
            "headers": JSON_HEADERS,
            "body": json.dumps({"error": str(exc), "code": exc.code}),
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": JSON_HEADERS,
            "body": json.dumps({"error": str(exc)}),
        }
