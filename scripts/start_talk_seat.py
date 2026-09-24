#!/usr/bin/env python3
"""Start irc_agent for a talk seat with nick {machine}-{agent pid} (--auto-nick)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from bobreport import normalize_machine_id


def _agent_script() -> Path:
    return Path(__file__).resolve().parent / "irc_agent.py"


def build_argv(args: argparse.Namespace) -> list[str]:
    mid = normalize_machine_id(args.machine)
    if not mid:
        raise SystemExit("INFO bad --machine id")
    home = str(Path(args.home).expanduser())
    nick = f"{mid}-0"
    return [
        sys.executable,
        "-u",
        str(_agent_script()),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--channel",
        args.channel,
        "--home",
        home,
        "--nick",
        nick,
        "--auto-nick",
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Spawn irc_agent with talk-seat nick suffix = agent PID"
    )
    p.add_argument("--machine", required=True)
    p.add_argument(
        "--home",
        default=os.path.join(os.path.expanduser("~"), ".agentic-irc-cursor"),
    )
    p.add_argument("--host", default="irc.ntsa.uk")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument(
        "--channel",
        default="",
        help="comma-separated JOIN list (default #bobiverse,#<machine>,#agentic_irc)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print argv only; do not spawn",
    )
    args = p.parse_args(argv)
    mid = normalize_machine_id(args.machine) or args.machine.strip().lower()
    if not args.channel:
        args.channel = f"#bobiverse,#{mid},#agentic_irc"
    os.environ.setdefault("AGENTIC_IRC_SEAT_PID", "self")
    cmd = build_argv(args)
    if args.dry_run:
        print(" ".join(cmd), flush=True)
        return 0
    proc = subprocess.Popen(cmd)
    print(f"INFO start_talk_seat agent pid={proc.pid} home={args.home}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
