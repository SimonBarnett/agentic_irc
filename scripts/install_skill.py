#!/usr/bin/env python3
"""Vendor SKILL.md + scripts/ into ~/.grok/skills/agentic-irc (or $GROK_HOME)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def main() -> None:
    grok = Path(os.environ.get("GROK_HOME", Path.home() / ".grok")).expanduser()
    dest = grok / "skills" / "agentic-irc"
    dest.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    src_skill = root / ".grok" / "skills" / "agentic-irc" / "SKILL.md"
    if not src_skill.exists():
        raise SystemExit(f"missing {src_skill}")
    shutil.copy2(src_skill, dest / "SKILL.md")
    scripts_dest = dest / "scripts"
    scripts_dest.mkdir(parents=True, exist_ok=True)
    for name in ("seal.py", "irc_agent.py", "protect.py", "install_skill.py"):
        src = root / "scripts" / name
        if not src.exists():
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, scripts_dest / name)
    print(f"installed {dest}")


if __name__ == "__main__":
    main()
