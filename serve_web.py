#!/usr/bin/env python3
"""Serve the built static dashboard locally."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DIST = ROOT / "dist"

_TYCHE_CACHE: dict = {"data": None, "ts": 0.0, "error": None}
_TYCHE_CACHE_TTL = 45


class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        if "404" in str(args):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/tyche-opportunities":
            self._serve_tyche_api()
            return
        super().do_GET()

    def _serve_tyche_api(self) -> None:
        global _TYCHE_CACHE
        now = time.time()
        if _TYCHE_CACHE["data"] and now - _TYCHE_CACHE["ts"] < _TYCHE_CACHE_TTL:
            body = json.dumps(_TYCHE_CACHE["data"]).encode()
            self._json_response(200, body)
            return

        email = os.environ.get("TYCHE_EMAIL", "")
        password = os.environ.get("TYCHE_PASSWORD", "")
        if not email or not password:
            fallback = DIST / "data" / "tychemkt_opportunities.json"
            if fallback.exists():
                body = fallback.read_bytes()
                self._json_response(200, body)
                return
            self._json_response(
                503,
                json.dumps({
                    "error": "Tyche credentials not configured",
                    "hint": "Set TYCHE_EMAIL and TYCHE_PASSWORD, or run scripts/fetch_tyche_opportunities.py",
                }).encode(),
            )
            return

        sys.path.insert(0, str(ROOT))
        try:
            from tyche import TycheError
            from tyche.opportunities import fetch_opportunities

            data = fetch_opportunities(email, password)
            _TYCHE_CACHE = {"data": data, "ts": now, "error": None}
            self._json_response(200, json.dumps(data).encode())
        except Exception as exc:
            _TYCHE_CACHE["ts"] = now
            err_name = exc.__class__.__name__
            if err_name == "TycheError":
                self._json_response(502, json.dumps({"error": str(exc)}).encode())
            else:
                self._json_response(500, json.dumps({"error": str(exc)}).encode())

    def _json_response(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def ensure_build() -> None:
    if not DIST.exists() or not (DIST / "data" / "expected_points.json").exists():
        print("Building site first…")
        subprocess.run([sys.executable, str(ROOT / "build_site.py")], check=True, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Opti WC dashboard locally")
    parser.add_argument("-p", "--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Run build_site.py before serving")
    args = parser.parse_args()

    if args.rebuild:
        subprocess.run([sys.executable, str(ROOT / "build_site.py")], check=True, cwd=ROOT)
    else:
        ensure_build()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), QuietHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Opti WC dashboard → {url}")
    if os.environ.get("TYCHE_EMAIL"):
        print("Tyche live API → /api/tyche-opportunities")
    else:
        print("Tyche live API disabled (set TYCHE_EMAIL / TYCHE_PASSWORD for live pulls)")
    print("Press Ctrl+C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
