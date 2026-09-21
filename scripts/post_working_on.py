#!/usr/bin/env python3
"""POST worker working_on (or idle) to the digest webhook. Change only."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import bobcallback

DEFAULT_URL = "http://127.0.0.1:17700/bob/v1/report"


def report_url() -> str:
    return (
        (os.environ.get("AGENTIC_IRC_REPORT_URL") or os.environ.get("BOB_REPORT_URL") or "")
        .strip()
        or DEFAULT_URL
    )


def post(machine: str, pid: int, working_on: str, nick: str, kind: str, state: str) -> int:
    secret = bobcallback.load_secret()
    if not secret:
        print("INFO no report.secret; skip POST", flush=True)
        return 0
    body = json.dumps(
        {
            "op": "merge",
            "machine": machine,
            "pid": int(pid),
            "nick": nick,
            "kind": kind,
            "state": state,
            "online": True,
            "working_on": working_on,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        report_url(),
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Bob-Secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def main() -> int:
    p = argparse.ArgumentParser(description="POST working_on or idle to /bob/v1/report")
    p.add_argument("--machine", required=True)
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--nick", default="")
    p.add_argument("--kind", default="cursor")
    p.add_argument("--working-on", default="")
    p.add_argument("--idle", action="store_true")
    args = p.parse_args()
    wo = "" if args.idle else (args.working_on or "").strip()
    state = "idle" if not wo else "running"
    nick = (args.nick or "").strip() or f"{args.machine}-{args.pid}"
    code = post(args.machine, args.pid, wo, nick, args.kind, state)
    print(f"INFO report POST {code} machine={args.machine} pid={args.pid} state={state}", flush=True)
    return 0 if code in (0, 200, 204) else 1


if __name__ == "__main__":
    raise SystemExit(main())
