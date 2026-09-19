#!/usr/bin/env python3
"""Operator helper: wrap JSON jobs as DUMB v1 lines on outbox."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protect
import seal


def _home(h: str) -> Path:
    os.environ["AGENTIC_IRC_HOME"] = str(Path(h).expanduser())
    return seal.home()


def _key(home: Path) -> bytes:
    p = home / "dumb" / "connector.key"
    return protect.read_secret_bytes(p)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--home", required=True)
    p.add_argument("--channel", default="#ops")
    p.add_argument("--from-nick", required=True)
    p.add_argument("--to", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("sysinfo")
    e = sub.add_parser("exec")
    e.add_argument("--argv", nargs="+", required=True)
    g = sub.add_parser("get")
    g.add_argument("--path", required=True)
    u = sub.add_parser("put")
    u.add_argument("--path", required=True)
    u.add_argument("--in", dest="infile", required=True)
    args = p.parse_args()
    home = _home(args.home)
    key = _key(home)
    jid = secrets.token_hex(8)
    job = {"v": 1, "op": args.cmd, "id": jid}
    if args.cmd == "exec":
        job["argv"] = args.argv
    if args.cmd == "get":
        job["path"] = args.path
    if args.cmd == "put":
        job["path"] = args.path
        job["b64"] = seal.b64(Path(args.infile).read_bytes())
    blob = seal.dumb_seal_bytes(json.dumps(job).encode(), key, args.channel, args.to, args.from_nick, jid)
    for ln in seal.dumb_irc_lines(blob, args.to, args.from_nick, jid):
        (home / "outbox.txt").open("a", encoding="utf-8").write(ln + "\n")
    print(jid)


if __name__ == "__main__":
    main()
