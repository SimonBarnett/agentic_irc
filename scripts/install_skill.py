#!/usr/bin/env python3
"""Vendor skills + scripts into $GROK_HOME/skills/."""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

SCRIPTS = (
    "seal.py",
    "irc_agent.py",
    "protect.py",
    "install_skill.py",
    "wire.py",
    "moot.py",
    "filexfer.py",
    "dumb_agent.py",
    "dumb_ctl.py",
    "beacon.py",
    "moot_thin_proto.py",
    "bobreport.py",
    "bobcallback.py",
    "bobtalk.py",
    "bobstat.py",
    "grok_talk.py",
    "grok_talk_drain.py",
    "irc_listen.py",
)
SKILLS = (
    "agentic-irc",
    "agentic-moot",
    "agentic-file",
    "agentic-dumb",
    "invite-airc",
    "bob-irc",
)
COPY_SCRIPTS = (
    "agentic-irc",
    "agentic-moot",
    "agentic-file",
    "agentic-dumb",
    "invite-airc",
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    grok = Path(os.environ.get("GROK_HOME", Path.home() / ".grok")).expanduser()
    root = Path(__file__).resolve().parents[1]
    if args.list:
        for s in SKILLS:
            print(s)
        for n in SCRIPTS:
            print(n)
        return
    for skill in SKILLS:
        dest = grok / "skills" / skill
        dest.mkdir(parents=True, exist_ok=True)
        src = root / ".grok" / "skills" / skill / "SKILL.md"
        shutil.copy2(src, dest / "SKILL.md")
        print(dest / "SKILL.md")
        if skill not in COPY_SCRIPTS:
            continue
        scripts_dest = dest / "scripts"
        scripts_dest.mkdir(parents=True, exist_ok=True)
        for name in SCRIPTS:
            sp = root / "scripts" / name
            if sp.exists():
                shutil.copy2(sp, scripts_dest / name)
                print(scripts_dest / name)
    req = root / "requirements.txt"
    if req.exists():
        shutil.copy2(req, grok / "skills" / "agentic-irc" / "requirements.txt")


if __name__ == "__main__":
    main()
