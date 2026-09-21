#!/usr/bin/env python3
"""Drain grok-outbox.jsonl completions into outbox.txt (for Watch or one-shot)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grok_talk  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Drain grok-talk completions to outbox.txt")
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME")
    p.add_argument("--outbox", default="", help="Override outbox path")
    args = p.parse_args()
    raw = args.home or os.environ.get("AGENTIC_IRC_HOME") or ""
    home = Path(raw).expanduser() if raw else Path.home() / ".agentic-irc-bobiverse"
    if args.home:
        os.environ["AGENTIC_IRC_HOME"] = str(home)
    outbox = Path(args.outbox).expanduser() if args.outbox else None
    lines = grok_talk.drain_completions_to_outbox(home, outbox=outbox)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
