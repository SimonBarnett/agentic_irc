#!/usr/bin/env python3
"""Write-only ionos digest callback. POST /bob/v1/report only — no GET digest."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bobreport

REPORT_PATH = "/bob/v1/report"
SECRET_ENV = "BOB_REPORT_SECRET"
ALLOW_ENV = "BOB_REPORT_ALLOW"


def secret_path() -> Path:
    return Path.home() / ".grok" / "bob" / "report.secret"


def load_secret() -> str:
    env = (os.environ.get(SECRET_ENV) or "").strip()
    if env:
        return env
    path = secret_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_allow_ips() -> set[str]:
    raw = (os.environ.get(ALLOW_ENV) or "").strip()
    if raw:
        return {p.strip() for p in raw.split(",") if p.strip()}
    return {"127.0.0.1", "::1"}


def handle_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes | str,
    peer_ip: str,
    home: Path,
    secret: str,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
) -> tuple[int, bytes]:
    """Pure request handler. No sockets. GET/HEAD never return digest bytes."""
    verb = (method or "").upper()
    route = (path or "").split("?", 1)[0]
    allow = allow_ips if allow_ips is not None else load_allow_ips()
    if route != REPORT_PATH:
        return 404, b""
    if verb in ("GET", "HEAD"):
        return 405, b""
    if verb != "POST":
        return 405, b""
    ip = (peer_ip or "").split("%", 1)[0]
    if allow and ip not in allow:
        return 403, b""
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    got = (hdrs.get("x-bob-secret") or "").strip()
    if not secret or got != secret:
        return 401, b""
    if isinstance(body, bytes):
        raw = body.decode("utf-8", "replace")
    else:
        raw = body or ""
    if bobreport.looks_like_secret(raw):
        return 400, b""
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return 400, b""
    if not isinstance(payload, dict):
        return 400, b""
    ok, _err, _actions = bobreport.apply_callback(home, payload, briefer_nick)
    if not ok:
        return 400, b""
    return 204, b""


class ReportHandler:
    """stdlib BaseHTTPRequestHandler mixin state. Instantiated by serve()."""

    home: Path
    secret: str
    allow_ips: set[str]
    briefer_nick: str


def make_handler(home: Path, secret: str, allow_ips: set[str], briefer_nick: str = ""):
    from http.server import BaseHTTPRequestHandler

    class _Handler(BaseHTTPRequestHandler):
        def _run(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            peer = (self.client_address or ("", 0))[0]
            code, payload = handle_request(
                method,
                self.path,
                {k: v for k, v in self.headers.items()},
                body,
                peer,
                home,
                secret,
                allow_ips,
                briefer_nick,
            )
            self.send_response(code)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload and method != "HEAD":
                self.wfile.write(payload)

        def do_GET(self) -> None:
            self._run("GET")

        def do_HEAD(self) -> None:
            self._run("HEAD")

        def do_POST(self) -> None:
            self._run("POST")

        def do_PUT(self) -> None:
            self._run("PUT")

        def log_message(self, _fmt: str, *_args: object) -> None:
            return

    return _Handler


def serve(
    home: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    secret: str | None = None,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
):
    """Blocking write-only listener. GET never returns digest.json."""
    from http.server import ThreadingHTTPServer

    handler = make_handler(home, secret if secret is not None else load_secret(), allow_ips or load_allow_ips(), briefer_nick)
    httpd = ThreadingHTTPServer((host, int(port)), handler)
    return httpd


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="write-only POST /bob/v1/report")
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME (digest.json)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("BOB_REPORT_PORT") or "0"))
    args = p.parse_args()
    home = Path(args.home).expanduser() if args.home else bobreport.digest_path(Path(".")).parent
    httpd = serve(home, host=args.bind, port=args.port)
    host, port = httpd.server_address[:2]
    print(f"INFO report listen {host}:{port} POST {REPORT_PATH} only", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
