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
    ok, _err = bobreport.apply_callback(home, payload, briefer_nick)
    if not ok:
        return 400, b""
    return 204, b""
