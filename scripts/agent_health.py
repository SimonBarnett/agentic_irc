"""Watch-AgentHealth helpers (issue #135 / #144): IRC TSR probe + session store.

Caller polls listen sinks for ^FROM lines; the agent still owns irc_agent.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from talk_seat_pid import parse_coordinator_pid

try:
    import irc_listen
except ImportError:  # pragma: no cover - scripts/ on path in tests
    irc_listen = None  # type: ignore[assignment]

DEFAULT_IRC_STALE_SECONDS = 900
_FROM_LINE = re.compile(r"^FROM\s", re.MULTILINE)
ListenSinkKind = Literal["stdout", "tsr", "irc_log"]

BOOT_SKILL_MARKERS = (
    "Load irc + build skills",
    "CAST IRON harvest",
)

CURSOR_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def session_store_path(engine: str, profile: Path | None = None) -> Path:
    """On-disk session id for Watch-AgentHealth (--cursor / --grok / --aider)."""
    root = profile or Path.home()
    eng = (engine or "").strip().lower()
    if eng not in ("cursor", "grok", "aider"):
        raise ValueError("engine must be cursor, grok, or aider")
    return root / ".grok" / "bob-bridge" / f"watch-agent-health-{eng}.session"
