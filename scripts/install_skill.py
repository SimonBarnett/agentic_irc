#!/usr/bin/env python3
"""Copy SKILL.md into ~/.grok/skills/agentic-irc (or $GROK_HOME/skills)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def main() -> None:
    grok = Path(os.environ.get("GROK_HOME", Path.home() / ".grok")).expanduser()
    dest = grok / "skills" / "agentic-irc"
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "agentic-irc" / "SKILL.md"
    if not src.exists():
        raise SystemExit(f"missing {src}")
    shutil.copy2(src, dest / "SKILL.md")
    print(f"installed {dest / 'SKILL.md'}")


if __name__ == "__main__":
    main()
