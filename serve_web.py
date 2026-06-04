#!/usr/bin/env python3
"""Serve the built static dashboard locally."""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"


class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        if "404" in str(args):
            super().log_message(fmt, *args)


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
