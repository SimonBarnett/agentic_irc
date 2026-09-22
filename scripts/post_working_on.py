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
    """Append PRIVMSG to worker outbox so #{machine} sees the job with the webhook."""
    import bobreport

    mid = bobreport.normalize_machine_id(machine)
    text = (working_on or "").strip()
    who = (nick or "").strip()
    if not mid or not text or not who:
        return
    if bobreport.looks_like_secret(text):
        return
    if home:
        root = Path(home).expanduser()
    else:
        env_home = (
            os.environ.get("AGENTIC_IRC_HOME") or os.environ.get("BOB_IRC_HOME") or ""
        ).strip()
        parsed = bobreport.parse_worker_nick(who)
        if parsed:
            base = Path.home() / ".agentic-irc-bobiverse"
            root = bobreport.worker_home(base, parsed[0], parsed[1])
        elif env_home:
            root = Path(env_home).expanduser()
        else:
            root = Path.home() / ".agentic-irc-bobiverse"
    outbox = root / "outbox.txt"
    try:
        outbox.parent.mkdir(parents=True, exist_ok=True)
        shop = bobreport.shop_channel(mid)
        line = bobreport.working_on_shop_line(who, text)
        with outbox.open("a", encoding="utf-8") as fh:
            fh.write(f"PRIVMSG {shop} :{line}\n")
        print(f"INFO shop outbox {outbox} -> {shop}", flush=True)
    except OSError as exc:
        print(f"INFO shop outbox skip: {exc}", flush=True)


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
        # Simon 2026-09-22: webhook description BEFORE idle, same event as shop say.
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
        enqueue_shop_working_on(args.machine, nick, desc)
        idle = base_payload(args.machine, args.pid, nick, args.kind, "idle")
        idle["working_on"] = desc
        code = post(idle)
        print(
            "INFO report POST %s idle machine=%s pid=%s" % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
    elif wo:
        work = base_payload(args.machine, args.pid, nick, args.kind, "running")
        work["working_on"] = wo
        code = post(work)
        print(
            "INFO report POST %s working_on machine=%s pid=%s" % (code, args.machine, args.pid),
            flush=True,
        )
        codes.append(code)
        # Same moment as webhook: queue shop PRIVMSG for the worker irc_agent.
        enqueue_shop_working_on(args.machine, nick, wo)
    if not codes:
        print("INFO nothing to POST; pass --create and/or --working-on or --idle", flush=True)
        return 1
    return 0 if all(c in (0, 200, 204) for c in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())