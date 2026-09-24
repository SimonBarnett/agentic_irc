#!/usr/bin/env python3
"""POST worker create, then working_on or idle, to the digest webhook."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import bobcallback
import talk_seat_pid

DEFAULT_URL = "http://irc.ntsa.uk:80/bob/v1/report"


def report_url() -> str:
    return (
        (os.environ.get("AGENTIC_IRC_REPORT_URL") or os.environ.get("BOB_REPORT_URL") or "")
        .strip()
        or DEFAULT_URL
    )


def post(payload: dict) -> int:
    secret = bobcallback.load_secret()
    if not secret:
        print("INFO no report.secret; skip POST", flush=True)
        return 0
    body = json.dumps(payload).encode("utf-8")
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def enqueue_shop_working_on(machine: str, nick: str, working_on: str, home: str | None = None) -> None:
    """No-op (issue #167). working_on is webhook-only; bob-* ACTION comes from digest."""
    return


def base_payload(machine: str, pid: int, nick: str, kind: str, state: str) -> dict:
    return {
        "op": "merge",
        "machine": machine,
        "pid": int(pid),
        "nick": nick,
        "kind": kind,
        "state": state,
        "online": True,
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create worker first, then POST working_on or idle"
    )
    p.add_argument("--machine", required=True)
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--nick", default="")
    p.add_argument("--kind", default="cursor")
    p.add_argument("--working-on", default="")
    p.add_argument("--agent", default="", help="worker agent name when known")
    p.add_argument("--model", default="", help="model name when known")
    p.add_argument("--create", action="store_true")
    p.add_argument("--idle", action="store_true")
    args = p.parse_args()
    nick = (args.nick or "").strip() or "%s-%s" % (args.machine, args.pid)
    err = talk_seat_pid.check_nick_seat_pid(nick, args.pid)
    if err:
        print(err, flush=True)
        return 2
    wo = "" if args.idle else (args.working_on or "").strip()
    codes = []
    if args.create or wo or args.idle:
        created = base_payload(args.machine, args.pid, nick, args.kind, "running")
        code = post(created)
        print(
            "INFO report POST %s create machine=%s pid=%s" % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
    if args.idle:
        # Webhook description BEFORE idle (issue #105); no IRC shop line (#167).
        desc = (args.working_on or "idle").strip() or "idle"
        marked = base_payload(args.machine, args.pid, nick, args.kind, "running")
        marked["working_on"] = desc
        code = post(marked)
        print(
            "INFO report POST %s pre-idle working_on machine=%s pid=%s"
            % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
        idle = base_payload(args.machine, args.pid, nick, args.kind, "idle")
        code = post(idle)
        print(
            "INFO report POST %s idle machine=%s pid=%s" % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
    elif wo:
        work = base_payload(args.machine, args.pid, nick, args.kind, "running")
        work["working_on"] = wo
        if (args.agent or "").strip():
            work["agent"] = args.agent.strip()
        if (args.model or "").strip():
            work["model"] = args.model.strip()
        code = post(work)
        print(
            "INFO report POST %s working_on machine=%s pid=%s" % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
    if not codes:
        print("INFO nothing to POST; pass --create and/or --working-on or --idle", flush=True)
        return 1
    return 0 if all(c in (0, 200, 204) for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())