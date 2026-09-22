#!/usr/bin/env python3
"""Spawn a shop-only worker irc_agent (MUST 2 / #70).

Uses bobreport.worker_irc_agent_args. Call from agentic_build when a git
worker process starts so NAMES #ionos lists w-io-<pid> alongside bob-ionos.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import bobreport

SCRIPTS = Path(__file__).resolve().parent


def default_fleet_home() -> str:
    for key in ("BOB_IRC_HOME", "AGENTIC_IRC_HOME"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return os.path.expanduser(raw)
    return os.path.expanduser("~/.agentic-irc-bobiverse")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fleet-home", default=default_fleet_home())
    ap.add_argument("--machine-id", required=True)
    ap.add_argument("--pid", required=True, help="worker OS pid (nick suffix)")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--host", default=os.environ.get("AGENTIC_IRC_HOST", "irc.ntsa.uk"))
    ap.add_argument("--port", default=os.environ.get("AGENTIC_IRC_PORT", "6697"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    launch = bobreport.worker_irc_agent_args(args.fleet_home, args.machine_id, args.pid)
    home = Path(launch["home"])
    agent = SCRIPTS / "irc_agent.py"
    cmd = [
        args.python,
        "-u",
        str(agent),
        "--host",
        str(args.host),
        "--port",
        str(args.port),
        "--channel",
        launch["channel"],
        "--home",
        launch["home"],
        "--nick",
        launch["nick"],
    ]
    if args.dry_run:
        print(" ".join(cmd))
        return 0
    home.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        cmd,
        cwd=str(SCRIPTS),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    print(f"started {launch['nick']} channel={launch['channel']} home={launch['home']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())